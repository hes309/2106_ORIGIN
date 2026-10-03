#!/usr/bin/env python3
"""
《2056：ORIGIN》纰漏检查工具 - 第二阶段：Claude批量审查
需要先运行 extract_knowledge.py 生成 knowledge/ 目录

用法：
  python check_consistency.py [模式] [选项]

模式：
  global    - 全局一致性检查（使用知识库文件，不需要原文）
  batch     - 逐批原文审查（每次送3章，检查章内逻辑）
  chapter   - 审查指定章节，如：chapter 001 002 003

选项：
  --from N  - batch模式从第N章开始（断点续传）
  --report  - 只输出最终报告，不显示过程

示例：
  python check_consistency.py global
  python check_consistency.py batch
  python check_consistency.py batch --from 020
  python check_consistency.py chapter 001 002 003
"""

import os
import sys
import json
import time
import re
from pathlib import Path
from anthropic import Anthropic

# ─── 配置 ──────────────────────────────────────────────
KNOWLEDGE_DIR = Path('knowledge')
CHAPTERS_DIR = KNOWLEDGE_DIR / 'chapters'
REPORT_FILE = Path('纰漏检查报告.md')
PROGRESS_FILE = Path('.check_progress.json')

BATCH_SIZE = 3           # 每批审查几章（建议3-5，视章节字数调整）
MAX_CHARS_PER_BATCH = 12000  # 每批原文字符上限（超出则缩减批次大小）
MODEL = 'claude-opus-4-5'    # 使用最强模型确保审查质量

client = Anthropic()

# ─── Prompt模板（强制不偷懒） ────────────────────────────

GLOBAL_CHECK_SYSTEM = """你是一位严格的科幻小说专业编辑，专门负责长篇小说的一致性审查。
你的任务是找出真实存在的纰漏，而不是给出笼统评语。
你必须：
1. 给出具体的矛盾描述，注明涉及的章节名称
2. 引用原文中的具体描述作为依据（不得捏造）
3. 对每条纰漏评估严重程度：🔴严重（影响核心逻辑）/ 🟡中等（影响阅读体验）/ 🟢轻微（细节瑕疵）
4. 不得以"整体一致性良好"等话术敷衍，必须穷举所有可疑之处
5. 如果某类确实没有发现问题，写"[本次未发现明确矛盾]"，但必须说明检查了哪些内容"""

GLOBAL_CHECK_USER_TEMPLATE = """以下是科幻小说《2056：ORIGIN》的结构化数据，请执行【{check_type}】专项检查。

{data}

---
请按以下格式输出检查结果：

## {check_type}检查报告

### 发现的纰漏（逐条列出，不得省略）

**纰漏1**
- 严重程度：🔴/🟡/🟢
- 涉及章节：
- 问题描述：（具体说明矛盾所在）
- 原文依据：（引用两处相互矛盾的描述）
- 建议修改方向：

（继续列出所有发现的纰漏）

### 需要人工进一步核查的疑点
（列出你不确定是否构成矛盾、需要结合原文确认的地方）

### 本次检查覆盖范围说明
（说明你检查了哪些内容，以便后续核实）"""

BATCH_CHECK_SYSTEM = """你是一位严格的科幻小说专业编辑，正在逐章审查《2056：ORIGIN》。
这是一部涵盖6卷+终章的长篇科幻小说，背景为2036-2126年，涉及AI、火星殖民、意识上传等主题。

你的审查任务：
1. 本批次内部的逻辑自洽性（时间线、因果、人物行为动机）
2. 与前情摘要（如有）的衔接是否顺畅
3. 人物行为是否符合其已建立的性格设定
4. 技术细节是否出现内部矛盾

严格要求：
- 必须引用原文具体句子作为依据
- 严重程度必须标注：🔴严重 / 🟡中等 / 🟢轻微
- 不得以"本批次写作流畅"等话术代替实质审查
- 如无问题，必须说明你检查了哪些具体内容后得出此结论"""

BATCH_CHECK_USER_TEMPLATE = """请审查以下{batch_count}章内容，寻找纰漏、矛盾和逻辑漏洞。

{prev_context}

---
【本批次原文】

{chapters_content}

---
请输出：

## 第{batch_label}批审查报告（{chapter_titles}）

### 本批次内部问题
（逐条列出所有发现的纰漏，无问题则写[未发现内部矛盾]并说明检查内容）

### 与前情的衔接问题
（如有前情摘要，检查衔接是否流畅）

### 人物动机与行为一致性
（检查本批次中人物的选择是否符合其设定）

### 时间线与因果逻辑
（检查本批次中的时间描述和事件因果）

### 需要跨章核查的疑点
（本批次中可能与其他章节矛盾但无法在当前上下文确认的内容）

### 本批次前情摘要（供下一批使用）
（用300字以内概括本批次关键事件、人物状态变化，格式：章节→发生了什么→人物状态）"""

# ────────────────────────────────────────────────────────


def load_knowledge_file(filename: str) -> str:
    path = KNOWLEDGE_DIR / filename
    if not path.exists():
        print(f'⚠️  知识库文件不存在：{path}，请先运行 extract_knowledge.py')
        sys.exit(1)
    return path.read_text(encoding='utf-8')


def load_chapter_files() -> list[dict]:
    if not CHAPTERS_DIR.exists():
        print('⚠️  chapters/ 目录不存在，请先运行 extract_knowledge.py')
        sys.exit(1)
    
    files = sorted(CHAPTERS_DIR.glob('*.txt'))
    chapters = []
    for f in files:
        content = f.read_text(encoding='utf-8')
        lines = content.split('\n')
        title = lines[0].strip()
        body = '\n'.join(lines[2:]).strip()
        chapters.append({
            'filename': f.name,
            'index': int(f.stem[:3]),
            'title': title,
            'content': body,
            'char_count': len(body),
        })
    return chapters


def call_claude(system: str, user: str, label: str) -> str:
    """调用Claude API，带重试逻辑"""
    print(f'  🤖 正在分析：{label}...')
    
    for attempt in range(3):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=system,
                messages=[{'role': 'user', 'content': user}]
            )
            return response.content[0].text
        except Exception as e:
            if attempt < 2:
                wait = (attempt + 1) * 10
                print(f'  ⚠️  请求失败（{e}），{wait}秒后重试...')
                time.sleep(wait)
            else:
                return f'[API调用失败：{e}]'


def save_progress(data: dict):
    PROGRESS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')


def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text(encoding='utf-8'))
    return {}


def append_report(content: str):
    with open(REPORT_FILE, 'a', encoding='utf-8') as f:
        f.write(content + '\n\n')


def init_report():
    REPORT_FILE.write_text(
        '# 《2056：ORIGIN》纰漏检查报告\n\n'
        f'生成时间：{time.strftime("%Y-%m-%d %H:%M")}\n\n'
        '---\n\n',
        encoding='utf-8'
    )


# ─── 模式一：全局一致性检查 ─────────────────────────────

def run_global_check():
    print('\n🌍 执行全局一致性检查（使用知识库文件）\n')
    
    checks = [
        ('时间线矛盾', 'timeline_clues.md', '时间线/逻辑'),
        ('人物设定一致性', 'character_mentions.md', '人物设定'),
        ('世界观/技术细节一致性', 'worldbuilding_mentions.md', '世界观与技术'),
    ]
    
    append_report('# 一、全局一致性检查\n')
    
    for check_name, filename, check_type in checks:
        print(f'\n📋 检查：{check_name}')
        data = load_knowledge_file(filename)
        
        # 如果文件太大，截断（全局检查不需要完整内容）
        if len(data) > 30000:
            data = data[:30000] + '\n\n[...文件过大，已截断至前30000字...]'
        
        user_prompt = GLOBAL_CHECK_USER_TEMPLATE.format(
            check_type=check_type,
            data=data
        )
        
        result = call_claude(GLOBAL_CHECK_SYSTEM, user_prompt, check_name)
        append_report(result)
        print(f'  ✅ 完成')
    
    print('\n✅ 全局检查完成，结果已写入报告')


# ─── 模式二：逐批原文审查 ───────────────────────────────

def run_batch_check(start_from: int = 0):
    print(f'\n📚 执行逐批原文审查（从第{start_from+1}章开始）\n')
    
    chapters = load_chapter_files()
    total = len(chapters)
    print(f'   共 {total} 章，每批 {BATCH_SIZE} 章')
    
    # 加载进度
    progress = load_progress()
    prev_summary = progress.get('prev_summary', '')
    
    append_report('# 二、逐批原文审查\n')
    
    i = start_from
    batch_num = start_from // BATCH_SIZE + 1
    
    while i < total:
        # 动态调整批次大小（避免超出token限制）
        batch = []
        total_chars = 0
        j = i
        while j < total and len(batch) < BATCH_SIZE:
            ch = chapters[j]
            if total_chars + ch['char_count'] > MAX_CHARS_PER_BATCH and batch:
                break
            batch.append(ch)
            total_chars += ch['char_count']
            j += 1
        
        # 拼接章节内容
        chapters_content = ''
        chapter_titles = ' | '.join(ch['title'] for ch in batch)
        for ch in batch:
            chapters_content += f'【{ch["title"]}】\n{ch["content"]}\n\n{"─"*40}\n\n'
        
        prev_context = ''
        if prev_summary:
            prev_context = f'【前情摘要（前{i}章）】\n{prev_summary}\n'
        
        user_prompt = BATCH_CHECK_USER_TEMPLATE.format(
            batch_count=len(batch),
            prev_context=prev_context,
            chapters_content=chapters_content,
            batch_label=batch_num,
            chapter_titles=chapter_titles,
        )
        
        print(f'\n📖 批次 {batch_num}：{chapter_titles}（{total_chars}字）')
        result = call_claude(BATCH_CHECK_SYSTEM, user_prompt,
                            f'批次{batch_num} ({chapter_titles})')
        
        append_report(result)
        
        # 提取前情摘要供下批使用
        summary_match = re.search(r'###\s*本批次前情摘要.*?\n(.*?)(?=###|\Z)', result, re.DOTALL)
        if summary_match:
            prev_summary = summary_match.group(1).strip()[:800]
        
        # 保存进度（支持断点续传）
        save_progress({
            'last_completed_chapter': j,
            'batch_num': batch_num,
            'prev_summary': prev_summary,
        })
        
        i = j
        batch_num += 1
        
        # 避免触发API频率限制
        if i < total:
            time.sleep(2)
    
    print('\n✅ 批量审查完成')


# ─── 模式三：指定章节审查 ───────────────────────────────

def run_chapter_check(chapter_indices: list[str]):
    print(f'\n🔍 审查指定章节：{", ".join(chapter_indices)}\n')
    
    all_chapters = load_chapter_files()
    idx_set = set(int(x) for x in chapter_indices)
    batch = [ch for ch in all_chapters if ch['index'] in idx_set]
    
    if not batch:
        print('⚠️  未找到指定章节')
        sys.exit(1)
    
    chapters_content = ''
    for ch in batch:
        chapters_content += f'【{ch["title"]}】\n{ch["content"]}\n\n{"─"*40}\n\n'
    
    chapter_titles = ' | '.join(ch['title'] for ch in batch)
    user_prompt = BATCH_CHECK_USER_TEMPLATE.format(
        batch_count=len(batch),
        prev_context='（单章审查模式，无前情摘要）',
        chapters_content=chapters_content,
        batch_label='自定义',
        chapter_titles=chapter_titles,
    )
    
    result = call_claude(BATCH_CHECK_SYSTEM, user_prompt, f'指定章节：{chapter_titles}')
    append_report(f'# 指定章节审查：{chapter_titles}\n\n' + result)
    print('\n✅ 指定章节审查完成')


# ─── 生成总结报告 ────────────────────────────────────────

def generate_summary():
    print('\n📊 生成汇总摘要...')
    
    report_content = REPORT_FILE.read_text(encoding='utf-8')
    
    # 提取所有🔴严重问题
    serious = re.findall(r'(?:严重程度：🔴.*?\n.*?涉及章节：.*?\n.*?问题描述：.+?)(?=\*\*纰漏|\n###)', 
                        report_content, re.DOTALL)
    
    summary = f'\n\n---\n\n# 📋 汇总：严重纰漏（🔴）一览\n\n'
    if serious:
        for i, s in enumerate(serious[:20], 1):
            summary += f'{i}. {s.strip()[:200]}\n\n'
    else:
        summary += '（需人工从完整报告中整理）\n'
    
    summary += f'\n\n---\n**报告生成完成。** 完整详情见上方各章节报告。\n'
    
    with open(REPORT_FILE, 'a', encoding='utf-8') as f:
        f.write(summary)


# ─── 主入口 ──────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    
    if not args:
        print(__doc__)
        sys.exit(0)
    
    mode = args[0]
    
    init_report()
    print(f'📄 报告将写入：{REPORT_FILE}')
    
    if mode == 'global':
        run_global_check()
    
    elif mode == 'batch':
        start = 0
        if '--from' in args:
            idx = args.index('--from')
            start = int(args[idx + 1]) - 1
        run_batch_check(start_from=start)
    
    elif mode == 'chapter':
        chapter_nums = [a for a in args[1:] if not a.startswith('--')]
        if not chapter_nums:
            print('⚠️  请指定章节编号，如：python check_consistency.py chapter 001 002 003')
            sys.exit(1)
        run_chapter_check(chapter_nums)
    
    else:
        print(f'⚠️  未知模式：{mode}')
        print('可用模式：global / batch / chapter')
        sys.exit(1)
    
    generate_summary()
    print(f'\n🎉 全部完成！报告文件：{REPORT_FILE}')


if __name__ == '__main__':
    main()
