import { ImageResponse } from "next/og";

export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "flex-start",
          padding: "80px",
          background: "linear-gradient(135deg, #0b0b0f 0%, #1a1a24 100%)",
          color: "white",
        }}
      >
        <div style={{ fontSize: 72, fontWeight: 700, display: "flex" }}>
          ipa-forge
        </div>
        <div
          style={{
            marginTop: 24,
            fontSize: 32,
            color: "#a1a1aa",
            maxWidth: 900,
            display: "flex",
          }}
        >
          A generic, data-driven iOS IPA patcher for AltStore Classic
          sideloading
        </div>
      </div>
    ),
    size,
  );
}
