#!/usr/bin/env python3
"""
《2056：ORIGIN》纰漏检查工具 - 第二阶段：生成可直接粘贴的审查Prompt
不需要API key，不需要任何第三方依赖。

用法：
    python3 generate_prompts.py

前提：先运行过 extract_knowledge.py，已生成 knowledge/ 目录。

输出：在 prompts/ 目录下生成多个 .txt 文件，
      每个文件是一个完整的对话prompt，直接复制粘贴给Claude即可。

生成的文件：
    prompts/00_全局_时间线检查.txt
    prompts/01_全局_人物设定检查.txt
    prompts/02_全局_世界观技术检查.txt
    prompts/03_批次_第001-003章.txt
    prompts/04_批次_第004-006章.txt
    ... （每批3章，依次类推）

使用方法：
    按顺序把每个 .txt 文件的内容粘贴给Claude，
    把Claude的回复保存到 replies/ 文件夹中对应的文件里。
"""

import re
import json
from pathlib import Path
from collections import defaultdict

KNOWLEDGE_DIR = Path('knowledge')
CHAPTERS_DIR  = KNOWLEDGE_DIR / 'chapters'
PROMPTS_DIR   = Path('prompts')

BATCH_SIZE = 3                 # 每批几章
MAX_CHARS_PER_BATCH = 10000   # 每批原文字符上限（超出自动缩减批次）

# ═══════════════════════════════════════════════════════
# Prompt 模板
# ═══════════════════════════════════════════════════════

SYSTEM_HEADER = """你是一位严格的科幻小说专业编辑，正在审查长篇科幻小说《2056：ORIGIN》的纰漏。

【审查要求，必须严格遵守】
1. 每条纰漏必须注明涉及的具体章节名称
2. 每条纰漏必须引用原文中相互矛盾的具体句子作为依据（不得捏造或模糊引用）
3. 每条纰漏必须标注严重程度：🔴严重（影响核心逻辑）/ 🟡中等（影响阅读体验）/ 🟢轻微（细节瑕疵）
4. 绝对禁止用"整体一致性良好""写作流畅"等话术代替实质审查
5. 如果某类确实没有发现问题，必须写"[未发现明确矛盾]"并说明你检查了哪些具体内容
6. 每条"需进一步核查的疑点"也要列出，不得因为不确定就略去

【输出格式】
## [检查类型]报告

### 发现的纰漏

**纰漏1**
- 严重程度：🔴/🟡/🟢
- 涉及章节：
- 问题描述：（具体说明矛盾所在）
- 原文依据A：（第一处描述）
- 原文依据B：（与A矛盾的第二处描述）
- 建议修改方向：

（继续列出所有发现的纰漏，编号不限）

### 需要人工进一步核查的疑点
（列出你不确定是否构成矛盾、需结合更多原文确认的地方）

### 本次检查覆盖范围说明
（说明你检查了哪些内容，防止遗漏）

"""

GLOBAL_TEMPLATE = """{system_header}
【本次任务：{check_type}专项检查】

以下是从全书自动提取的结构化数据，请仔细分析并找出所有矛盾和疑点。

{data}
"""

BATCH_TEMPLATE = """{system_header}
【本次任务：逐章原文深度审查】
【本批章节：{chapter_titles}】
【批次编号：第{batch_num}批 / 共{total_batches}批】

{prev_summary}

━━━━━━━━━━ 本批原文 ━━━━━━━━━━

{chapters_content}

━━━━━━━━━━ 审查要求 ━━━━━━━━━━

请对上述章节逐一检查以下四类问题：

1. **时间线与因果逻辑**
   检查本批次内的时间描述是否自洽，事件因果是否合理。

2. **人物动机与行为一致性**
   检查人物的选择和行为是否符合其已建立的性格与处境。

3. **与前情的衔接**
   检查本批次开头是否与前情摘要（如有）顺畅衔接，有无遗漏或矛盾。

4. **技术/世界观细节**
   检查本批次中涉及的技术描述、组织设定是否与前文一致。

审查完成后，请在最后附上：

### 本批次前情摘要（供下一批使用，限300字）
（格式：章节→关键事件→主要人物当前状态）
"""

# ═══════════════════════════════════════════════════════

def check_knowledge_dir():
    if not KNOWLEDGE_DIR.exists():
        print('❌ 未找到 knowledge/ 目录，请先运行：')
        print('   python3 extract_knowledge.py 2056_ORIGIN_手稿.md')
        exit(1)
    if not CHAPTERS_DIR.exists():
        print('❌ 未找到 knowledge/chapters/ 目录，请重新运行 extract_knowledge.py')
        exit(1)


def load_knowledge_file(filename):
    path = KNOWLEDGE_DIR / filename
    if not path.exists():
        print(f'⚠️  缺少文件：{path}')
        return ''
    return path.read_text(encoding='utf-8')


def load_chapter_files():
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


def truncate(text, max_chars, label=''):
    if len(text) <= max_chars:
        return text
    note = f'\n\n[...{label}内容过长，已截断至{max_chars}字，完整内容请查阅原始文件...]'
    return text[:max_chars] + note


def generate_global_prompts(prompts_dir):
    checks = [
        ('00_全局_时间线检查',   'timeline_clues.md',       '时间线与逻辑矛盾',
         '下方是全书所有章节中出现的时间线相关句子，请找出所有时间矛盾、逻辑倒置、前后不一致的问题。'),
        ('01_全局_人物设定检查', 'character_mentions.md',    '人物设定一致性',
         '下方是全书各核心人物在每章的出场片段，请找出人物性格、身份、能力、关系前后矛盾的问题。'),
        ('02_全局_世界观检查',   'worldbuilding_mentions.md','世界观与技术细节一致性',
         '下方是全书各章涉及技术设定、组织、系统能力的句子，请找出技术细节、设定描述前后矛盾的问题。'),
    ]

    for fname, data_file, check_type, task_desc in checks:
        print(f'  生成：{fname}.txt')
        data = load_knowledge_file(data_file)
        data = truncate(data, 40000, check_type)

        prompt = GLOBAL_TEMPLATE.format(
            system_header=SYSTEM_HEADER,
            check_type=check_type,
            data=f'【任务说明】\n{task_desc}\n\n{data}',
        )

        out_path = prompts_dir / f'{fname}.txt'
        out_path.write_text(prompt, encoding='utf-8')


def generate_batch_prompts(prompts_dir, chapters):
    total = len(chapters)
    batches = []

    # 切批（动态调整大小避免超字数限制）
    i = 0
    while i < total:
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
        batches.append(batch)
        i = j

    total_batches = len(batches)
    print(f'  共分 {total_batches} 批，每批 {BATCH_SIZE} 章（字数限制{MAX_CHARS_PER_BATCH}字/批）')

    for batch_idx, batch in enumerate(batches):
        batch_num = batch_idx + 1
        start_idx = batch[0]['index']
        end_idx   = batch[-1]['index']
        fname = f'{batch_num + 2:02d}_批次_{start_idx:03d}-{end_idx:03d}章'

        chapter_titles = ' | '.join(ch['title'] for ch in batch)

        chapters_content = ''
        for ch in batch:
            chapters_content += f'【{ch["title"]}】\n{"─"*30}\n{ch["content"]}\n\n'

        if batch_idx == 0:
            prev_summary = '【前情说明】这是第一批，无前情摘要。请从头开始审查。'
        else:
            prev_summary = (
                '【前情摘要】\n'
                '（请将上一批Claude回复中"本批次前情摘要"部分的内容粘贴到这里，'
                '替换掉这段文字，再把整个prompt发给Claude）'
            )

        prompt = BATCH_TEMPLATE.format(
            system_header=SYSTEM_HEADER,
            chapter_titles=chapter_titles,
            batch_num=batch_num,
            total_batches=total_batches,
            prev_summary=prev_summary,
            chapters_content=chapters_content,
        )

        out_path = prompts_dir / f'{fname}.txt'
        out_path.write_text(prompt, encoding='utf-8')
        print(f'  [{batch_num:2d}/{total_batches}] {fname}.txt  '
              f'（{sum(c["char_count"] for c in batch):,}字，{len(prompt):,}字符）')


def generate_readme(prompts_dir, total_batches):
    readme = f"""# 《2056：ORIGIN》纰漏检查 —— Prompt使用说明

## 操作步骤

### 第一步：全局检查（推荐先做）
把以下3个文件的内容分别粘贴给Claude，每次得到回复后保存：

1. `00_全局_时间线检查.txt` → 检查时间线矛盾
2. `01_全局_人物设定检查.txt` → 检查人物前后不一致
3. `02_全局_世界观检查.txt` → 检查技术/设定矛盾

### 第二步：逐批原文深度审查
共 {total_batches} 批，按编号顺序处理：

- 文件名格式：`03_批次_001-003章.txt`、`04_批次_004-006章.txt`……
- **每批结束后**，把Claude回复里"本批次前情摘要"部分的文字，
  复制粘贴到**下一批**prompt文件中标有
  `（请将上一批Claude回复中"本批次前情摘要"部分的内容粘贴到这里）`
  的位置，再发给Claude。
- 这样Claude每批都有上下文，不会丢失前情。

### 建议
- 把每次Claude的回复保存到 `replies/` 文件夹，文件名与prompt对应
- 全部跑完后，把所有reply文件里的🔴严重问题汇总到一个表格里

## 严重程度说明
- 🔴 严重：影响核心逻辑，读者会发现的真实矛盾，必须修改
- 🟡 中等：影响阅读体验，建议修改
- 🟢 轻微：细节瑕疵，可酌情处理
"""
    (prompts_dir / 'README.txt').write_text(readme, encoding='utf-8')


def main():
    check_knowledge_dir()

    PROMPTS_DIR.mkdir(exist_ok=True)
    (PROMPTS_DIR / 'replies').mkdir(exist_ok=True)

    print('\n📝 生成全局检查Prompt...')
    generate_global_prompts(PROMPTS_DIR)

    print('\n📚 加载章节文件...')
    chapters = load_chapter_files()
    print(f'   共 {len(chapters)} 章')

    print('\n📖 生成逐批审查Prompt...')
    generate_batch_prompts(PROMPTS_DIR, chapters)

    # 算批次数
    i, total_batches = 0, 0
    while i < len(chapters):
        batch, total_chars, j = [], 0, i
        while j < len(chapters) and len(batch) < BATCH_SIZE:
            ch = chapters[j]
            if total_chars + ch['char_count'] > MAX_CHARS_PER_BATCH and batch:
                break
            batch.append(ch); total_chars += ch['char_count']; j += 1
        total_batches += 1; i = j

    generate_readme(PROMPTS_DIR, total_batches)

    prompt_files = list(PROMPTS_DIR.glob('*.txt'))
    total_size   = sum(f.stat().st_size for f in prompt_files) // 1024

    print(f'''
✅ 完成！

📁 输出目录：prompts/
   Prompt文件：{len(prompt_files)} 个
   总大小：约 {total_size} KB

使用方法：
   1. 打开 prompts/README.txt 查看操作说明
   2. 按顺序把每个 .txt 文件粘贴给Claude
   3. 把回复保存到 prompts/replies/ 文件夹
''')


if __name__ == '__main__':
    main()
