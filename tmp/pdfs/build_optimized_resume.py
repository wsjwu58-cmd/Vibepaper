from __future__ import annotations

import os
from pathlib import Path

from fontTools.ttLib import TTFont as FontToolsTTFont
from fontTools.varLib.instancer import instantiateVariableFont
from PIL import Image as PILImage
from pypdf import PdfReader
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(r"E:\VibePaperProject")
SOURCE_PDF = Path(r"D:\download\New Resume 7b2743 (复制) (复制) (8).pdf")
WORK_DIR = ROOT / "tmp" / "pdfs" / "resume_build"
OUTPUT_DIR = ROOT / "output" / "pdf"
OUTPUT_PDF = OUTPUT_DIR / "武世杰-后端开发-Agent开发-优化版简历.pdf"

FONT_SOURCE = Path(r"C:\Windows\Fonts\NotoSansSC-VF.ttf")
FONT_REGULAR = WORK_DIR / "NotoSansSC-Regular.ttf"
FONT_BOLD = WORK_DIR / "NotoSansSC-Bold.ttf"
PORTRAIT = WORK_DIR / "portrait.jpg"


ACCENT = colors.HexColor("#1F5F8B")
TEXT = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#5B6773")
RULE = colors.HexColor("#D6DEE5")
PALE = colors.HexColor("#F4F7F9")


def prepare_assets() -> None:
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    if not FONT_SOURCE.exists():
        raise FileNotFoundError(f"Missing font: {FONT_SOURCE}")

    def set_font_identity(font: FontToolsTTFont, subfamily: str, postscript_suffix: str) -> None:
        family = "Noto Sans SC Resume"
        full_name = f"{family} {subfamily}"
        postscript_name = f"NotoSansSCResume-{postscript_suffix}"
        names = font["name"]
        names.names = [
            record
            for record in names.names
            if record.nameID not in {1, 2, 4, 6, 16, 17}
        ]
        for platform_id, encoding_id, language_id in (
            (3, 1, 0x0409),
            (1, 0, 0),
        ):
            names.setName(family, 1, platform_id, encoding_id, language_id)
            names.setName(subfamily, 2, platform_id, encoding_id, language_id)
            names.setName(full_name, 4, platform_id, encoding_id, language_id)
            names.setName(postscript_name, 6, platform_id, encoding_id, language_id)
            names.setName(family, 16, platform_id, encoding_id, language_id)
            names.setName(subfamily, 17, platform_id, encoding_id, language_id)

    variable_font = FontToolsTTFont(str(FONT_SOURCE))
    regular = instantiateVariableFont(variable_font, {"wght": 400}, inplace=False)
    set_font_identity(regular, "Regular", "Regular")
    regular["OS/2"].fsSelection &= ~(1 << 5)
    regular["OS/2"].fsSelection |= 1 << 6
    regular["head"].macStyle &= ~1
    regular.save(str(FONT_REGULAR))

    bold = instantiateVariableFont(variable_font, {"wght": 700}, inplace=False)
    set_font_identity(bold, "Bold", "Bold")
    bold["OS/2"].fsSelection |= 1 << 5
    bold["OS/2"].fsSelection &= ~(1 << 6)
    bold["head"].macStyle |= 1
    bold.save(str(FONT_BOLD))

    reader = PdfReader(str(SOURCE_PDF))
    images = reader.pages[0].images
    if not images:
        raise RuntimeError("No portrait image found in source PDF")
    PORTRAIT.write_bytes(images[0].data)

    with PILImage.open(PORTRAIT) as photo:
        photo = photo.convert("RGB")
        target_ratio = 4 / 5
        current_ratio = photo.width / photo.height
        if current_ratio > target_ratio:
            new_width = int(photo.height * target_ratio)
            left = (photo.width - new_width) // 2
            photo = photo.crop((left, 0, left + new_width, photo.height))
        elif current_ratio < target_ratio:
            new_height = int(photo.width / target_ratio)
            top = max(0, (photo.height - new_height) // 2)
            photo = photo.crop((0, top, photo.width, top + new_height))
        photo.save(PORTRAIT, quality=94)


def register_fonts() -> None:
    pdfmetrics.registerFont(TTFont("ResumeSans", str(FONT_REGULAR)))
    pdfmetrics.registerFont(TTFont("ResumeSans-Bold", str(FONT_BOLD)))
    pdfmetrics.registerFontFamily(
        "ResumeSans",
        normal="ResumeSans",
        bold="ResumeSans-Bold",
        italic="ResumeSans",
        boldItalic="ResumeSans-Bold",
    )


def p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(text, style)


def make_styles() -> dict[str, ParagraphStyle]:
    base = dict(
        fontName="ResumeSans",
        fontSize=9.4,
        leading=13.5,
        textColor=TEXT,
        wordWrap="CJK",
        alignment=TA_LEFT,
        allowWidows=0,
        allowOrphans=0,
    )
    tight = dict(base)
    tight["leading"] = 13.0
    summary = dict(base)
    summary.update(fontSize=9.1, leading=13.0, textColor=MUTED)
    return {
        "body": ParagraphStyle("body", **base),
        "body_tight": ParagraphStyle("body_tight", **tight),
        "summary": ParagraphStyle("summary", **summary),
        "name": ParagraphStyle(
            "name",
            fontName="ResumeSans-Bold",
            fontSize=23,
            leading=26,
            textColor=TEXT,
            wordWrap="CJK",
        ),
        "role": ParagraphStyle(
            "role",
            fontName="ResumeSans",
            fontSize=10.8,
            leading=14.4,
            textColor=ACCENT,
            wordWrap="CJK",
        ),
        "contact": ParagraphStyle(
            "contact",
            fontName="ResumeSans",
            fontSize=8.65,
            leading=12.7,
            textColor=MUTED,
            wordWrap="CJK",
        ),
        "section": ParagraphStyle(
            "section",
            fontName="ResumeSans-Bold",
            fontSize=11.4,
            leading=13.8,
            textColor=ACCENT,
            wordWrap="CJK",
        ),
        "title": ParagraphStyle(
            "title",
            fontName="ResumeSans-Bold",
            fontSize=9.9,
            leading=13.5,
            textColor=TEXT,
            wordWrap="CJK",
        ),
        "meta": ParagraphStyle(
            "meta",
            fontName="ResumeSans",
            fontSize=8.9,
            leading=13.0,
            textColor=MUTED,
            wordWrap="CJK",
        ),
        "label": ParagraphStyle(
            "label",
            fontName="ResumeSans-Bold",
            fontSize=9.0,
            leading=12.7,
            textColor=TEXT,
            wordWrap="CJK",
        ),
    }


def section_header(title: str, styles: dict[str, ParagraphStyle]) -> KeepTogether:
    bar = Table(
        [[p(title, styles["section"]), ""]],
        colWidths=[34 * mm, None],
        rowHeights=[6.1 * mm],
    )
    bar.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PALE),
                ("LINEBEFORE", (0, 0), (0, 0), 2.4, ACCENT),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LINEBELOW", (0, 0), (-1, -1), 0.45, RULE),
            ]
        )
    )
    return KeepTogether([Spacer(1, 2.0 * mm), bar, Spacer(1, 1.5 * mm)])


def title_row(
    left: str,
    middle: str,
    right: str,
    styles: dict[str, ParagraphStyle],
    widths: tuple[float, float, float] = (83 * mm, 51 * mm, 38 * mm),
) -> Table:
    row = Table(
        [[p(left, styles["title"]), p(middle, styles["meta"]), p(right, styles["meta"])]],
        colWidths=list(widths),
    )
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ALIGN", (2, 0), (2, 0), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    return row


def bullet(text: str, styles: dict[str, ParagraphStyle]) -> Table:
    row = Table(
        [[p("•", styles["body_tight"]), p(text, styles["body_tight"])]],
        colWidths=[4.3 * mm, 167.7 * mm],
    )
    row.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 1.8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.8),
                ("TEXTCOLOR", (0, 0), (0, 0), ACCENT),
            ]
        )
    )
    return row


def header(styles: dict[str, ParagraphStyle]) -> Table:
    photo = Image(str(PORTRAIT), width=25.6 * mm, height=32 * mm)
    identity = [
        p("武世杰", styles["name"]),
        Spacer(1, 0.7 * mm),
        p("后端开发 / Agent 开发", styles["role"]),
    ]
    contacts = [
        p(
            '<link href="mailto:wsjwu58@gmail.com" color="#5B6773">wsjwu58@gmail.com</link>'
            "<br/>13643452791",
            styles["contact"],
        ),
        p(
            '<link href="https://www.wsjaly.cn" color="#5B6773">www.wsjaly.cn</link>'
            "<br/>开发实验室负责人",
            styles["contact"],
        ),
    ]
    contact_table = Table([[contacts[0], contacts[1]]], colWidths=[47 * mm, 43 * mm])
    contact_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 1.5 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    block = Table(
        [[photo, identity, contact_table]],
        colWidths=[31 * mm, 51 * mm, 90 * mm],
        rowHeights=[32 * mm],
    )
    block.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ("LINEAFTER", (0, 0), (0, 0), 0.55, RULE),
            ]
        )
    )
    return block


def build_pdf() -> None:
    register_fonts()
    styles = make_styles()
    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=A4,
        leftMargin=19 * mm,
        rightMargin=19 * mm,
        topMargin=14 * mm,
        bottomMargin=12 * mm,
        title="武世杰 - 后端开发 / Agent 开发",
        author="武世杰",
        subject="后端开发与 Agent 开发简历",
        creator="Codex resume layout optimization",
        pageCompression=1,
    )

    story = [header(styles), Spacer(1, 3.0 * mm)]

    story += [
        section_header("教育经历", styles),
        title_row("中北大学", "软件工程", "2024/09 - 2028/07", styles),
    ]

    story += [
        section_header("实习经历", styles),
        title_row("欧电云", "Java 后端工程师", "2026/05 - 2026/08", styles),
        Spacer(1, 0.7 * mm),
        p(
            "负责欧电云 SaaS 零售平台订单核心系统开发，基于自研流程引擎维护订单创建、履约、取消及退款链路。",
            styles["summary"],
        ),
        Spacer(1, 0.4 * mm),
        bullet(
            "基于<b>联合状态机</b>实现订单主单、订单行、交货单及包裹状态流转，通过乐观锁将状态冲突率降低 <b>90%</b>。",
            styles,
        ),
        bullet(
            "排查并修复<b>新人券阶梯发放缺陷</b>，沿 OMS -> MQ -> Hermes 跨系统调用链定位根因；输出 4 个分级修复方案及 5 条回归用例。",
            styles,
        ),
        bullet(
            "负责<b>退款退货流程</b>开发，设计 rollBackMark 标记机制并串联库存、优惠券、积分、礼品卡及财务退款；处理效率提升 <b>60%+</b>，回滚成功率达 <b>99.9%</b>。",
            styles,
        ),
    ]

    story += [
        section_header("开源贡献", styles),
        title_row(
            "TriliumNext / Trilium (37.5k stars)",
            '<link href="https://github.com/TriliumNext/Trilium" color="#1F5F8B">GitHub 仓库</link>',
            "2026/08",
            styles,
            widths=(92 * mm, 42 * mm, 38 * mm),
        ),
        Spacer(1, 0.55 * mm),
        p(
            '<b>修复 Mermaid 图表渲染与导入识别</b>　<link href="https://github.com/TriliumNext/Trilium/pull/10856" color="#1F5F8B">PR #10856（已合并）</link>',
            styles["body"],
        ),
        bullet(
            "定位 Mermaid 多实例渲染中的<b>异步竞态</b>，完善 Markdown -> 编辑器 -> 全链路的 Mermaid 自动识别。",
            styles,
        ),
        bullet(
            "实现<b>串行渲染</b>与跨导入/编辑器的 Mermaid 源码识别，并按 review 意见完善资源清空及临时 DOM 清理。",
            styles,
        ),
        bullet(
            "PR 经 CI 与 maintainer 审核合并进 main；多图与 Markdown 导入场景下图表可稳定渲染。",
            styles,
        ),
    ]

    story += [
        section_header("项目经历", styles),
        title_row(
            "VibePaper - 节点化无限画布",
            "全栈开发",
            "2026/05 - 至今",
            styles,
        ),
        Spacer(1, 0.45 * mm),
        p(
            '<link href="https://github.com/wsjwu58-cmd/Vibepaper" color="#1F5F8B">github.com/wsjwu58-cmd/Vibepaper</link>',
            styles["meta"],
        ),
        Spacer(1, 0.3 * mm),
        p(
            "面向个人创作者的 AI 原生节点化多媒体创作平台，以无限画布为容器、节点为内容单元、Agent 驱动流程，覆盖创意、生成、编辑、组合与导出。",
            styles["summary"],
        ),
        Spacer(1, 0.25 * mm),
        p(
            "<b>技术栈：</b>Spring Cloud / MyBatis-Plus / FastAPI / LangGraph / Redis / RocketMQ / PostgreSQL",
            styles["body_tight"],
        ),
        bullet(
            "基于开源 <b>Pi Agent Core</b> 二次开发 Agent 服务，封装工厂注入、领域系统提示词与工具白名单。",
            styles,
        ),
        bullet(
            "面向竖屏短剧工业化生产设计 <b>Agent 领域状态机</b>，固化格式规范、角色档案、ShotSpec、关键帧与渲染谱系；以 PostgreSQL JSONB 落地，覆盖 7 个状态机场景测试。",
            styles,
        ),
        bullet(
            "实现<b>乐观锁并发保存协议</b>（版本比对、冲突拒绝、前端刷新）与高频防抖保存（500 ms + 关页 flush），避免多端与 Agent 并发写覆盖。",
            styles,
        ),
        bullet(
            "设计“冻结-结算-解冻”点数计费模型：提交冻结预估点数、成功按实际用量结算，失败/取消/超时全额解冻，保障异步生成链路零资损。",
            styles,
        ),
    ]

    story += [
        section_header("专业技能", styles),
    ]
    skill_rows = [
        (
            "后端与数据",
            "Java、Python、Spring Cloud、FastAPI、MyBatis-Plus、Redis、RocketMQ、Elasticsearch、PostgreSQL、Docker",
        ),
        (
            "Agent 与效能",
            "Pi Agent Core、LangGraph、Codex、Claude Code、Copilot、SKILLS、MCP、GitHub Actions、Obsidian 自动化管线",
        ),
        (
            "工程与其他",
            "Git、IntelliJ IDEA；了解 Kotlin / Android；熟悉 Windows 逆向分析及 IDA、angr、pyc 等工具",
        ),
    ]
    skill_table = Table(
        [[p(label, styles["label"]), p(value, styles["body_tight"])] for label, value in skill_rows],
        colWidths=[26 * mm, 146 * mm],
    )
    skill_table.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0.8),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0.8),
                ("TEXTCOLOR", (0, 0), (0, -1), ACCENT),
            ]
        )
    )
    story.append(skill_table)

    doc.build(story)


if __name__ == "__main__":
    prepare_assets()
    build_pdf()
    print(OUTPUT_PDF)
