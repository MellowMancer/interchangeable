"""MCP tools over the comparison, so an agent can answer a dispensing question.

Lives in the app layer, never in `bdheal` — that package pins its runtime dependencies
deliberately, and an MCP dependency there would breach the isolation its tests enforce.
"""

from contextlib import contextmanager

from mcp.server.mcpserver import MCPServer

from ixq.adapters.sqlite import SqliteRepository, connect
from ixq.domain import Placement
from ixq.pipeline.diverge import compare
from ixq.settings import database_path

server = MCPServer(
    name="interchangeable",
    instructions=(
        "Compares UK drug labels across the manufacturers of one active substance. "
        "Every answer is scoped to the sections that were actually scanned: 'absent' "
        "means absent from those sections, never absent from the label."
    ),
)


@contextmanager
def _repository():
    """One connection per tool call — the server outlives any single request."""
    conn = connect(database_path())
    try:
        yield SqliteRepository(conn)
    finally:
        conn.close()


@server.tool(
    description=(
        "Where a clinical concept sits in each manufacturer's label for one substance. "
        "Answers questions like 'does this manufacturer contraindicate renal impairment?'"
    )
)
def label_says(substance: str, concept: str) -> dict:
    """One concept across every manufacturer, with the quote behind each answer."""
    with _repository() as repository:
        result = compare(substance, repository)
    if not result.products:
        return {"error": f"no labels stored for {substance!r}"}

    row = next((r for r in result.rows if r.concept == concept), None)
    if row is None:
        return {
            "substance": substance,
            "concept": concept,
            "found": False,
            "scanned_sections": list(result.scanned),
            "note": (
                f"{concept!r} was not matched in any scanned section of any label. "
                "That is not evidence it is absent from the labels themselves."
            ),
            "known_concepts": sorted(r.concept for r in result.rows),
        }

    return {
        "substance": substance,
        "concept": concept,
        "found": True,
        "diverges": row.diverges,
        "scanned_sections": list(result.scanned),
        "manufacturers": [
            {
                "name": p.ma_holder or p.external_id,
                "placement": row.placements[p.external_id].value,
                "meaning": _meaning(row.placements[p.external_id]),
            }
            for p in result.products
        ],
    }


@server.tool(
    description=(
        "Every concept where the manufacturers of one substance disagree, with the "
        "revision date of each label so staleness can be told from disagreement."
    )
)
def divergences(substance: str) -> dict:
    """The findings worth a prescriber's attention, and the context to judge them."""
    with _repository() as repository:
        result = compare(substance, repository)
    if not result.products:
        return {"error": f"no labels stored for {substance!r}"}

    revised = {d.product_external_id: d.last_updated for d in result.documents}
    return {
        "substance": substance,
        "scanned_sections": list(result.scanned),
        "caveat": (
            "'absent' means absent from the scanned sections only. A label may state the "
            "same thing in a section that was not collected."
        ),
        "manufacturers": [
            {"name": p.ma_holder or p.external_id, "revised": revised.get(p.external_id)}
            for p in result.products
        ],
        "divergent_concepts": [
            {
                "concept": row.concept,
                "placements": {
                    (p.ma_holder or p.external_id): row.placements[p.external_id].value
                    for p in result.products
                },
            }
            for row in result.divergent
        ],
        "agreed_concepts": [r.concept for r in result.rows if not r.diverges],
    }


def _meaning(placement: Placement) -> str:
    return {
        Placement.CONTRAINDICATION: "absolute contraindication (section 4.3)",
        Placement.WARNING: "warning or precaution (section 4.4)",
        Placement.INTERACTION: "interaction (section 4.5)",
        Placement.PREGNANCY: "pregnancy or lactation (section 4.6)",
        Placement.ABSENT: "not found in any scanned section",
    }[placement]


def main() -> None:
    """Serve over stdio, which is how an MCP client launches this."""
    server.run("stdio")
