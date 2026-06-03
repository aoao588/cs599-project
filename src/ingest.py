"""Ingestion script: scan data/corpus/, split, embed, write to Chroma.

Usage:
    python -m src.ingest                       # full rebuild from default corpus dir
    python -m src.ingest --path data/corpus/hr # ingest a sub-directory
    python -m src.ingest --no-reset            # add to existing collection
"""
from __future__ import annotations

import argparse
from pathlib import Path

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from .vectorstore import get_vectorstore, reset_collection

CORPUS_ROOT = Path("data/corpus")
CHUNK_SIZE = 500
CHUNK_OVERLAP = 80


def load_markdown_docs(root: Path) -> list[Document]:
    docs: list[Document] = []
    for path in sorted(root.rglob("*.md")):
        text = path.read_text(encoding="utf-8")
        rel = path.relative_to(CORPUS_ROOT).as_posix()
        docs.append(Document(page_content=text, metadata={"source": rel}))
    return docs


def split_docs(docs: list[Document]) -> list[Document]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n## ", "\n### ", "\n\n", "\n", "。", "！", "？", " ", ""],
    )
    return splitter.split_documents(docs)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=str(CORPUS_ROOT), help="corpus directory")
    parser.add_argument(
        "--no-reset",
        action="store_true",
        help="append to existing collection instead of rebuilding",
    )
    args = parser.parse_args()

    root = Path(args.path)
    if not root.exists():
        raise SystemExit(f"corpus dir not found: {root}")

    if not args.no_reset:
        print("[ingest] resetting collection ...")
        reset_collection()

    print(f"[ingest] scanning {root} ...")
    raw_docs = load_markdown_docs(root)
    if not raw_docs:
        raise SystemExit(f"no .md files under {root}")
    print(f"[ingest] loaded {len(raw_docs)} files")

    chunks = split_docs(raw_docs)
    print(f"[ingest] split into {len(chunks)} chunks")

    vs = get_vectorstore()
    vs.add_documents(chunks)
    print(f"[ingest] done — collection size: {vs._collection.count()}")


if __name__ == "__main__":
    main()
