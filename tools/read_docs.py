import os
import sys
from docx import Document
from docx.oxml.text.paragraph import CT_P
from docx.oxml.table import CT_Tbl
from docx.text.paragraph import Paragraph
from docx.table import Table

def dump_docx(file_path, output_txt_path):
    doc = Document(file_path)
    lines = []
    lines.append("=" * 60)
    lines.append(f"DOCUMENT: {os.path.basename(file_path)}")
    lines.append("=" * 60 + "\n")

    para_count = 0
    table_count = 0
    block_count = 0

    for child in doc.element.body:
        block_count += 1
        if isinstance(child, CT_P):
            para_count += 1
            p = Paragraph(child, doc)
            text = p.text.strip()
            style_name = p.style.name if p.style else "Normal"
            if text:
                lines.append(f"[P style='{style_name}'] {text}")
            else:
                lines.append("[EMPTY_P]")
        elif isinstance(child, CT_Tbl):
            table_count += 1
            t = Table(child, doc)
            lines.append(f"\n--- [TABLE #{table_count}: {len(t.rows)} rows x {len(t.columns)} cols] ---")
            for r_idx, row in enumerate(t.rows):
                # de-duplicate cells if merged
                row_cells = []
                seen_cells = set()
                for c_idx, cell in enumerate(row.cells):
                    txt = cell.text.strip().replace("\r", " ").replace("\n", " <BR> ")
                    row_cells.append(f"Col{c_idx}: {txt}")
                lines.append(f"  Row {r_idx}: " + " | ".join(row_cells))
            lines.append(f"--- [END TABLE #{table_count}] ---\n")
        else:
            lines.append(f"[OTHER_ELEMENT: {child.tag}]")

    lines.append(f"\nSummary for {os.path.basename(file_path)}:")
    lines.append(f"Total elements: {block_count}, Paragraphs: {para_count}, Tables: {table_count}\n")

    with open(output_txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"Dumped {os.path.basename(file_path)}: {para_count} paras, {table_count} tables to {output_txt_path}")

if __name__ == "__main__":
    base_dir = r"D:\ClaimCheck_Pro"
    files = [
        "ClaimCheck_Pro_零费用架构项目概述.docx",
        "ClaimCheck_Pro_零费用架构实施步骤.docx"
    ]
    for fn in files:
        fp = os.path.join(base_dir, fn)
        out_fp = os.path.join(base_dir, "tools", fn.replace(".docx", ".txt"))
        dump_docx(fp, out_fp)
