import { ImageResponse } from "next/og";

/**
 * The card platforms render when the URL is pasted into a chat or a feed.
 *
 * Generated rather than a checked-in bitmap so it cannot drift from the palette: the
 * colours below are the placement fills, and a reader who has seen the card recognises
 * the table when they arrive.
 *
 * No web font is loaded. `ImageResponse` would have to fetch one at request time, and a
 * social crawler that times out gets no card at all — a worse outcome than the fallback
 * face. The layout carries the identity instead.
 */
export const runtime = "nodejs";
export const alt =
  "Interchangeable? — where the manufacturers of the same active substance disagree about its label.";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const PAPER = "#fbfaf8";
const INK = "#1a1714";
const MUTED = "#6b635b";
const RULE = "#e2ddd6";
/**
 * Three manufacturers, two sections — the shape of a divergence, not a claim about the
 * corpus. Deliberately illustrative: the card is fetched by crawlers that will not wait
 * for an API call, and a card asserting live counts would go stale the moment one more
 * label is collected.
 */
const FILLS = ["#8c1d18", "#1f4e79", "#1f4e79"];

export default function OpengraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: PAPER,
          color: INK,
          padding: 72,
        }}
      >
        <div style={{ display: "flex", fontSize: 30, letterSpacing: -0.5 }}>
          Interchangeable
          <span style={{ color: FILLS[0] }}>?</span>
        </div>

        <div style={{ display: "flex", flexDirection: "column", gap: 28 }}>
          <div style={{ display: "flex", fontSize: 68, lineHeight: 1.1, maxWidth: 900 }}>
            Same drug. Different manufacturer. Different label.
          </div>

          <div style={{ display: "flex", gap: 16 }}>
            {FILLS.map((fill, column) => (
              <div key={column} style={{ display: "flex", flexDirection: "column", gap: 10 }}>
                <div style={{ display: "flex", width: 150, height: 26, background: fill }} />
                <div style={{ display: "flex", fontSize: 20, color: MUTED }}>
                  {column === 0 ? "§4.3" : "§4.5"}
                </div>
              </div>
            ))}
          </div>
        </div>

        <div
          style={{
            display: "flex",
            borderTop: `1px solid ${RULE}`,
            paddingTop: 24,
            fontSize: 24,
            color: MUTED,
          }}
        >
          The same requirement, filed in different sections. Every claim carries its quote.
        </div>
      </div>
    ),
    size,
  );
}
