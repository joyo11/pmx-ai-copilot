import { ImageResponse } from "next/og";

// PMX AI favicon — white "P" on deep navy with a blue accent ring
// (brand: navy #071F3A + blue #3B93F0). Next.js auto-routes this as the
// app-wide favicon, replacing the old default favicon.ico.

export const size = { width: 32, height: 32 };
export const contentType = "image/png";

export default function Icon() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          background: "#071F3A",
          color: "#FFFFFF",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: 22,
          fontFamily: "system-ui, -apple-system, sans-serif",
          fontWeight: 800,
          letterSpacing: "-0.04em",
          borderRadius: 8,
          border: "1.5px solid #3B93F0",
        }}
      >
        P
      </div>
    ),
    {
      ...size,
    },
  );
}
