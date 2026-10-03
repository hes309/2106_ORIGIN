#!/usr/bin/env python3
"""
《2056：ORIGIN》纰漏检查工具 - 第一阶段：结构提取
用法：python extract_knowledge.py <md文件路径>
"""

import re
import json
import sys
from pathlib import Path
from collections import defaultdict

INPUT_FILE = sys.argv[1] if len(sys.argv) > 1 else "2056_ORIGIN_手稿.md"

TIME_KEYWORDS = [
    r'\d{4}年', r'\d+月', r'\d+日', r'\d+天后', r'\d+小时后', r'\d+分钟后',
    r'第\d+天', r'翌日', r'次日', r'当晚', r'当天', r'同一天', r'同一时间',
    r'同一刻', r'此时', r'此刻', r'不久后', r'几天后', r'几小时后',
    r'数年后', r'数十年后', r'一年后', r'三年后', r'七十年',
]

CORE_CHARACTERS = [
    '陆星阈', '沈存真', '伊芙', '伊芙-9', 'ORIGIN', 'ATHENA',
    '诺亚', '诺亚·凯恩', '伊莱', '伊莱·默森', '艾登', '艾登·沃斯',
    '陆知夏', '知夏', '岑望霁', '梁澈', '苏眠', '结衣', '井上',
]

WORLDBUILDING_KEYWORDS = [
    'ORIGIN', 'ATHENA', '伊芙-9', 'SKY VAULT', '天穹阵列',
    '方舟', 'ARK', '黑色一分钟', '自由火种', 'NEXUS CORE',
    '棱镜智能', '量子', '脑机接口', '神经接口', '近地轨道',
    '火星', '月球', '上传', '仿生', '新公民', '数字文明',
    '隔离协议', '深空', '白色圆环', '文明风险',
]


def load_text(path: str) -> str:
    with open(path, 'r', encoding='utf-8') as f:
        return f.read()


def parse_chapters(text: str) -> list:
    """
    解析所有章节。文件有三种章节标题格式：
    - 第一卷正文：  # 第X章：标题          （一级标题）
    - 第二至六卷：  ### 第X章：《标题》     （三级标题，在 ## 第N卷 下）
    - 终章：        ### 一、《标题》         （三级标题，在 ## 终章 下）
    同时跳过目录区（173行之前均为目录/作品信息）
    """
    lines = text.split('\n')
    
    # 卷标题模式（二级标题）
    vol_pattern   = re.compile(r'^##\s+第([一二三四五六七八九十]+)卷[：:《]')
    ep_vol_pattern = re.compile(r'^##\s+终章')
    
    # 章节标题：一级 or 三级
    ch1_pattern = re.compile(r'^#\s+第([一二三四五六七八九十百零\d]+)章[：:]\s*(.+)')   # 第一卷
    ch3_pattern = re.compile(r'^###\s+第([一二三四五六七八九十百零\d]+)章[：:]\s*[《]?(.+?)[》]?\s*$')  # 二至六卷
    ep_pattern  = re.compile(r'^###\s+([一二三四五六七八九十]+)[、，]\s*[《]?(.+?)[》]?\s*$')            # 终章
    
    BODY_START_LINE = 172   # 正文开始行（0-indexed）

    # 先全文扫描所有卷标题行，建立「行号→卷名」有序列表
    vol_declarations = []
    for i, line in enumerate(lines):
        vm = vol_pattern.match(line)
        if vm:
            v = f'第{vm.group(1)}卷'
            m2 = re.search(r'[：:《](.+)', line)
            if m2:
                v += f'：{m2.group(1).strip("《》 ")}'
            vol_declarations.append((i, v))
        em = ep_vol_pattern.match(line)
        if em:
            vol_declarations.append((i, '终章：永恒之后'))

    # 第一卷正文(L173-L1767)没有在正文中重声明卷标题，需要特殊处理
    # 正文中第一个卷声明是L1769（第二卷），所以1769行之前全属第一卷
    FIRST_VOL_NAME = '第一卷：黑色一分钟'
    body_vol_decls = [(li, vn) for li, vn in vol_declarations if li >= BODY_START_LINE]

    def get_vol_at_line(line_idx):
        current = FIRST_VOL_NAME
        for decl_line, vol_name in body_vol_decls:
            if decl_line <= line_idx:
                current = vol_name
            else:
                break
        return current

    chapter_starts = []   # (line_idx, vol, ch_num, title)

    for i, line in enumerate(lines):
        if i < BODY_START_LINE:
            continue

        # 一级章节（第一卷）
        m1 = ch1_pattern.match(line)
        if m1:
            chapter_starts.append((i, get_vol_at_line(i), m1.group(1), m1.group(2).strip()))
            continue
        # 三级章节（第二至六卷）
        m3 = ch3_pattern.match(line)
        if m3:
            chapter_starts.append((i, get_vol_at_line(i), m3.group(1), m3.group(2).strip()))
            continue
        # 终章节
        me = ep_pattern.match(line)
        vol_here = get_vol_at_line(i)
        if me and vol_here.startswith('终章'):
            chapter_starts.append((i, vol_here, me.group(1), me.group(2).strip()))
            continue

    # 切割内容
    chapters = []
    for idx, (line_i, vol, ch_num, title) in enumerate(chapter_starts):
        end_i = chapter_starts[idx+1][0] if idx+1 < len(chapter_starts) else len(lines)
        content_lines = lines[line_i+1:end_i]
        # 过滤掉子标题行（## 时间戳 之类），只保留正文
        content_lines = [l for l in content_lines
                         if not re.match(r'^#{1,3}\s+\d{2}:\d{2}', l)]
        content = '\n'.join(content_lines).strip()
        content = re.sub(r'\n---+\n?', '\n\n', content).strip()

        if vol.startswith('终章'):
            full_title = f'[终章] {ch_num}、{title}'
        else:
            title = title.strip('《》')
        full_title = f'[{vol}] 第{ch_num}章：{title}'

        chapters.append({
            'vol': vol,
            'ch_num': ch_num,
            'title': title,
            'full_title': full_title,
            'content': content,
            'start_line': line_i + 1,
            'char_count': len(content),
        })

    return chapters


def extract_timeline_clues(chapters):
    pattern = re.compile('|'.join(TIME_KEYWORDS))
    results = []
    for ch in chapters:
        clues = []
        for sent in re.split(r'[。！？…\n]', ch['content']):
            sent = sent.strip()
            if sent and pattern.search(sent) and len(sent) > 5:
                clues.append(sent[:120])
        if clues:
            results.append({'chapter': ch['full_title'], 'clues': clues[:8]})
    return results


def extract_character_mentions(chapters):
    char_data = defaultdict(list)
    for ch in chapters:
        for char in CORE_CHARACTERS:
            if char in ch['content']:
                sentences = re.split(r'[。！？…]', ch['content'])
                mentions = [s.strip()[:100] for s in sentences
                            if char in s and len(s.strip()) > 5][:3]
                if mentions:
                    char_data[char].append({'chapter': ch['full_title'], 'snippets': mentions})
    return dict(char_data)


def extract_worldbuilding_mentions(chapters):
    results = []
    for ch in chapters:
        found = {}
        for sent in re.split(r'[。！？…]', ch['content']):
            sent = sent.strip()
            if len(sent) < 8:
                continue
            for kw in WORLDBUILDING_KEYWORDS:
                if kw in sent and kw not in found:
                    found[kw] = sent[:120]
        if found:
            results.append({'chapter': ch['full_title'], 'mentions': found})
    return results


def generate_chapter_summaries(chapters):
    summaries = []
    for ch in chapters:
        paragraphs = [p.strip() for p in ch['content'].split('\n\n') if p.strip()]
        first_sentences = []
        for para in paragraphs[:5]:
            first = re.split(r'[。！？…]', para)[0].strip()
            if first and len(first) > 3:
                first_sentences.append(first[:80])
        summaries.append({
            'chapter': ch['full_title'],
            'char_count': ch['char_count'],
            'skeleton': first_sentences,
        })
    return summaries


def save_outputs(out_dir, chapters, timeline, characters, worldbuilding, summaries):
    out_dir.mkdir(parents=True, exist_ok=True)

    index = [{'full_title': c['full_title'], 'vol': c['vol'],
               'char_count': c['char_count'], 'start_line': c['start_line']} for c in chapters]
    (out_dir / 'chapter_index.json').write_text(
        json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')

    tl_md = '# 时间线线索提取\n\n> 供Claude进行时间线矛盾检查。\n\n'
    for item in timeline:
        tl_md += f'## {item["chapter"]}\n'
        for clue in item['clues']:
            tl_md += f'- {clue}\n'
        tl_md += '\n'
    (out_dir / 'timeline_clues.md').write_text(tl_md, encoding='utf-8')

    char_md = '# 核心人物出场记录\n\n> 供Claude检查人物设定是否前后一致。\n\n'
    for char, appearances in characters.items():
        char_md += f'## {char}（共出现{len(appearances)}章）\n'
        for app in appearances:
            char_md += f'\n**{app["chapter"]}**\n'
            for s in app['snippets']:
                char_md += f'- {s}\n'
        char_md += '\n'
    (out_dir / 'character_mentions.md').write_text(char_md, encoding='utf-8')

    wb_md = '# 世界观与技术概念出现记录\n\n> 供Claude检查技术设定是否前后矛盾。\n\n'
    for item in worldbuilding:
        wb_md += f'## {item["chapter"]}\n'
        for kw, sent in item['mentions'].items():
            wb_md += f'- **[{kw}]** {sent}\n'
        wb_md += '\n'
    (out_dir / 'worldbuilding_mentions.md').write_text(wb_md, encoding='utf-8')

    sk_md = '# 章节内容骨架\n\n> 每章前5段首句，用于快速定位情节。\n\n'
    for item in summaries:
        sk_md += f'## {item["chapter"]}（{item["char_count"]}字）\n'
        for s in item['skeleton']:
            sk_md += f'- {s}\n'
        sk_md += '\n'
    (out_dir / 'chapter_skeletons.md').write_text(sk_md, encoding='utf-8')

    chapters_dir = out_dir / 'chapters'
    chapters_dir.mkdir(exist_ok=True)
    for i, ch in enumerate(chapters):
        safe_title = re.sub(r'[\\/:*?"<>|\[\]]', '_', ch['full_title'])
        fname = f'{i+1:03d}_{safe_title}.txt'
        content = f'{ch["full_title"]}\n{"="*40}\n\n{ch["content"]}'
        (chapters_dir / fname).write_text(content, encoding='utf-8')

    print(f'\n✅ 提取完成，输出目录：{out_dir}')
    print(f'   章节总数：{len(chapters)}')
    print(f'   时间线线索：{sum(len(t["clues"]) for t in timeline)} 条')
    print(f'   人物记录：{len(characters)} 个角色')
    print(f'   世界观条目：{sum(len(w["mentions"]) for w in worldbuilding)} 条')
    print(f'\n📁 文件列表：')
    for f in sorted(out_dir.iterdir()):
        if f.is_file():
            print(f'   {f.name}  ({f.stat().st_size // 1024} KB)')
    print(f'   chapters/  ({len(chapters)} 个章节文件)')


def main():
    print(f'📖 读取文件：{INPUT_FILE}')
    text = load_text(INPUT_FILE)
    print(f'   文件大小：{len(text):,} 字符')

    print('🔍 解析章节结构...')
    chapters = parse_chapters(text)
    print(f'   识别到 {len(chapters)} 个章节')

    print('⏱  提取时间线线索...')
    timeline = extract_timeline_clues(chapters)
    print('👥 提取人物出场记录...')
    characters = extract_character_mentions(chapters)
    print('🌍 提取世界观/技术细节...')
    worldbuilding = extract_worldbuilding_mentions(chapters)
    print('📝 生成章节骨架...')
    summaries = generate_chapter_summaries(chapters)

    out_dir = Path('knowledge')
    save_outputs(out_dir, chapters, timeline, characters, worldbuilding, summaries)


if __name__ == '__main__':
    main()
