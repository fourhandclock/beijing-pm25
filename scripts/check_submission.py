"""Verify submission source links, numerical claims and rendered document bounds.

This checks the generated PDF layout and editable PPTX structure. It does not
pretend to invoke Microsoft's PowerPoint renderer, which is not a dependency.
"""

import hashlib
import json
import math
from pathlib import Path
import re

import pandas as pd
import pymupdf
from pptx import Presentation


ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def normalize(text):
    return re.sub(r"\s+", " ", text).strip()


def check_scheduling_metadata(text, location):
    if re.search(r"\bdeadline\b|\b(?:24|25)\s+Nov(?:ember)?\s+2026\b|2026-11-(?:24|25)",text,re.I):
        raise ValueError(f"Administrative scheduling metadata remains in {location}")


def main():
    directory = ROOT / "submission"
    manifest = json.loads((directory/"build_manifest.json").read_text())
    if "deadline" in manifest or not manifest["stage3_is_exploratory"] or not manifest["neutral_title_pages"]:
        raise ValueError("Submission metadata differs from the approved scope")
    for section in ("input_sha256", "output_sha256"):
        for name, expected in manifest[section].items():
            if sha(ROOT/name) != expected:
                raise ValueError(f"Stale submission {section}: {name}; rebuild documents")
    frames = {}
    for claim in manifest["numerical_claims"]:
        name = claim["source"]
        if name not in frames:
            frames[name] = pd.read_csv(ROOT/name)
        data = frames[name]
        selected = pd.Series(True, index=data.index)
        for column, expected in claim["where"].items():
            selected &= data[column].eq(expected)
        if selected.sum() != 1:
            raise ValueError(f"Numerical claim no longer identifies one row: {claim}")
        actual = float(data.loc[selected,claim["column"]].iloc[0])
        if (not math.isclose(actual,claim["value"],rel_tol=1e-12,abs_tol=1e-12)
                or format(actual,claim["format"]) != claim["display"]):
            raise ValueError(f"Numerical claim differs from its generated source: {claim}")

    research_docs = ["README.md","PROJECT_BRIEF.md","reports/reproducibility.md",
                     "reports/stage1_summary.md","reports/stage2_analysis.md",
                     "reports/stage2_checks.md","reports/stage2_protocol.md",
                     "reports/stage3_extensions.md","reports/stage4_verification.md",
                     "reports/stage4/statistical_audit.md","reports/stage4/pr_review_summary.md",
                     "submission/report.md","submission/speaker_notes.md"]
    for name in research_docs:
        check_scheduling_metadata((ROOT/name).read_text(),name)

    pdf_results = {}
    for filename in ("report.pdf", "slides.pdf"):
        with pymupdf.open(directory/filename) as doc:
            texts = []
            for page in doc:
                text = page.get_text()
                check_scheduling_metadata(text,f"{filename} page {page.number+1}")
                if len(text.strip()) < 70 or "\ufffd" in text or "\x00" in text:
                    raise ValueError(f"Blank/unreadable text in {filename} page {page.number+1}")
                if filename=="report.pdf" and len(text.split())<100:
                    raise ValueError(f"Sparse/orphan report page {page.number+1}; review pagination")
                texts.append(normalize(text))
                for block in page.get_text("dict")["blocks"]:
                    for line in block.get("lines",[]):
                        for span in line["spans"]:
                            x0,y0,x1,y1 = span["bbox"]
                            if x0 < -1 or y0 < -1 or x1 > page.rect.width+1 or y1 > page.rect.height+1:
                                raise ValueError(f"Text outside {filename} page {page.number+1}: {span['text']}")
                # ReportLab embeds the DejaVu glyphs; inspect the actual PDF fonts.
                if not page.get_fonts():
                    raise ValueError(f"No font resources on {filename} page {page.number+1}")
            if filename == "slides.pdf" and len(doc) != manifest["slide_count"]:
                raise ValueError("Slide count differs between manifest and PDF")
            pdf_results[filename] = {"pages":len(doc), "nonblank_pages":True,
                                      "text_within_page_bounds":True,"replacement_glyphs":0}
            if filename == "report.pdf":
                combined = " ".join(texts)
                for required in ("AI assistance", "0.0618",
                                 "46.785", "exploratory", "same-day", "not independent scientific replication"):
                    if required not in combined:
                        raise ValueError(f"Missing required report content: {required}")

    content = json.loads((directory/"slide_content.json").read_text())
    if "deadline" in content or content["title"] != manifest["title"]:
        raise ValueError("Report and presentation metadata are inconsistent")
    references = manifest["references"]
    if content["slides"][-1]["references"] != references:
        raise ValueError("Report and presentation bibliographies differ")
    if len({s["layout"] for s in content["slides"]}) < 8:
        raise ValueError("Presentation compositions no longer reflect the revised design")
    if content["slides"][12].get("figure") != "station_profiles":
        raise ValueError("Clustering slide must use the existing verified profile visualization")
    presentation = Presentation(directory/"slides.pptx")
    if len(presentation.slides) != manifest["slide_count"]:
        raise ValueError("PPTX slide count differs from PDF")
    with pymupdf.open(directory/"slides.pdf") as doc:
        ppt_urls = set()
        for i,slide in enumerate(presentation.slides):
            for shape in slide.shapes:
                if (shape.left < 0 or shape.top < 0 or shape.left+shape.width > presentation.slide_width+2
                        or shape.top+shape.height > presentation.slide_height+2):
                    raise ValueError(f"PPTX shape outside slide {i+1}")
            if not slide.has_notes_slide or len(slide.notes_slide.notes_text_frame.text.strip()) < 60:
                raise ValueError(f"Speaker notes missing on slide {i+1}")
            check_scheduling_metadata(slide.notes_slide.notes_text_frame.text,f"slide {i+1} notes")
            for shape in slide.shapes:
                if shape.has_text_frame:
                    for para in shape.text_frame.paragraphs:
                        for run in para.runs:
                            if run.hyperlink.address:
                                ppt_urls.add(run.hyperlink.address)
            text = normalize(doc[i].get_text())
            for expected in (content["slides"][i]["title"],):
                if normalize(expected) not in text:
                    raise ValueError(f"PDF text missing/truncated on slide {i+1}: {expected}")
            # The PPTX stores exactly the same explicit line breaks as the PDF.
            ppt_text = normalize(" ".join(s.text for s in slide.shapes if s.has_text_frame))
            if ppt_text != text:
                raise ValueError(f"PDF and PPTX text differs on slide {i+1}")
            images = [e for e in content["elements"][i] if e["kind"]=="image"]
            texts = [e for e in content["elements"][i] if e["kind"]=="text"]
            for picture in images:
                a = pymupdf.Rect(picture["x"],picture["y"],picture["x"]+picture["w"],picture["y"]+picture["h"])
                for box in texts:
                    b = pymupdf.Rect(box["x"],box["y"],box["x"]+box["w"],box["y"]+box["h"])
                    if (a&b).get_area()>1:
                        raise ValueError(f"Image overlaps a text box on slide {i+1}")
        slide_urls = {link["uri"] for page in doc for link in page.get_links() if "uri" in link}
    with pymupdf.open(directory/"report.pdf") as doc:
        report_urls = {link["uri"] for page in doc for link in page.get_links() if "uri" in link}
    for _,url in references:
        if url not in ppt_urls or url not in slide_urls or url not in report_urls:
            raise ValueError(f"Bibliographic link missing from a document: {url}")
    for value in (presentation.core_properties.title,presentation.core_properties.subject):
        check_scheduling_metadata(value,"PowerPoint properties")
    result = {"status":"passed", "source_and_output_hashes_checked":True,
              "source_linked_numerical_claims_checked":len(manifest["numerical_claims"]),
              "pdf_checks":pdf_results,"pptx_slides":len(presentation.slides),
              "pptx_shape_bounds_and_speaker_notes_checked":True,
              "pdf_and_pptx_text_identical":True,
              "bibliographies_and_reference_links_match":True,
              "active_research_documents_omit_scheduling_metadata":True,
              "slide_image_and_text_boxes_do_not_overlap":True,
              "distinct_slide_layouts":len({s["layout"] for s in content["slides"]}),
              "native_powerpoint_rendering_checked":False,
              "visual_review":"See reports/stage5_refinement.md for the recorded rendered-image review; automatic checks do not establish visual quality."}
    target = ROOT/"reports/verification"
    target.mkdir(parents=True,exist_ok=True)
    (target/"submission_check.json").write_text(json.dumps(result,indent=2)+"\n")
    print(json.dumps(result,indent=2))


if __name__ == "__main__":
    main()
