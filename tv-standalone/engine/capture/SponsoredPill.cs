using System;
using System.Runtime.InteropServices;

/// <summary>Exact fixed-location YouTube TV Sponsored pill matcher; not a general ad classifier.</summary>
public static class SponsoredPill
{
    public const double Threshold = 300.0;
    public const string TemplateSha256 = "7c774e11abddb704234b512b746e4e48655517078ed1b6217e2ecd6fbcbcb983";
    // Embedded from commercial-vision-lab/sponsored_template.json: x18,y24,width64,height12.
    // The one-pixel surround is x17..82,y23..36 in the 480x270 reference frame.
    private static readonly byte[] Weights = new byte[] {
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 86, 87, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 93, 38, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 120, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 131, 92, 0, 0, 92, 135, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 103, 0, 14, 62, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 97, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 70, 0, 0, 0, 0, 0, 0, 74, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 124, 12, 0, 0, 64, 57, 19, 69, 0, 103, 0, 119, 0, 132, 0, 130, 0, 116, 0, 120, 0, 131, 0, 132, 0,
        115, 53, 0, 101, 0, 104, 0, 133, 0, 117, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 156, 0, 0, 0, 0, 0, 0, 159, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 106, 0, 43, 0, 0, 89, 13, 0, 0, 103, 0, 88, 0, 102, 0, 53, 58, 0, 0, 73, 0, 33, 0,
        97, 0, 0, 90, 51, 107, 0, 58, 0, 98, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 111, 0, 0, 155, 0, 0, 0, 114, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 115, 0, 0, 28, 48, 0, 0, 77, 0, 39, 0, 117, 0, 97, 0, 110, 0, 63, 0, 96, 0, 111, 0, 93, 0,
        114, 0, 0, 67, 0, 0, 0, 101, 0, 112, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 143, 0, 0, 0, 0, 0, 0, 145, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 96, 55, 0, 55, 0, 90, 0, 0, 31, 87, 0, 0, 89, 0, 103, 0, 0, 92, 0, 0, 0, 91, 0, 0,
        112, 0, 0, 0, 107, 0, 0, 12, 61, 70, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 117, 0, 0, 110, 105, 0, 0, 120, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 90, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 167, 0, 0, 0, 0, 166, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 64, 160, 160, 63, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
        0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    };

    /// <summary>Score tightly packed RGB888 at exactly 480x270, matching the Python reference.</summary>
    public static double ScoreRgb(byte[] rgb, int width = 480, int height = 270)
    {
        if (rgb == null) throw new ArgumentNullException(nameof(rgb));
        if (width != 480 || height != 270) throw new ArgumentOutOfRangeException(nameof(width), "RGB reference must be 480x270");
        if (rgb.Length != 480 * 270 * 3) throw new ArgumentException("RGB byte count must equal width*height*3", nameof(rgb));
        Span<int> gray = stackalloc int[66 * 14];
        for (int oy = 23; oy < 37; oy++)
            for (int ox = 17; ox < 83; ox++)
            {
                int offset = (oy * 480 + ox) * 3;
                gray[(oy - 23) * 66 + ox - 17] = Luma(rgb[offset], rgb[offset + 1], rgb[offset + 2]);
            }
        return Score(gray);
    }

    /// <summary>
    /// Score the same reference ROI directly from NV12 planes. Full-range BT.601 conversion
    /// and floor-coordinate nearest-neighbor sampling match capture/Program.cs exactly.
    /// Caller must retain valid readable Y (pitch*height bytes) and UV (pitch*height/2 bytes)
    /// planes for this call. Pointer lengths cannot be discovered or checked by this API.
    /// No full frame, PNG, image library, native DLL, or image-file access is used.
    /// </summary>
    public static double ScoreNv12(IntPtr y, IntPtr uv, int width, int height, int pitch)
    {
        if (width < 2 || width > 4096 || height < 2 || height > 2304 || (width & 1) != 0 || (height & 1) != 0)
            throw new ArgumentOutOfRangeException(nameof(width), "NV12 geometry must be even and within 2..4096 x 2..2304");
        // Bound every signed IntPtr.Add offset, including padded chroma rows.
        if (pitch < width || pitch > Int32.MaxValue / height || (pitch & 1) != 0)
            throw new ArgumentOutOfRangeException(nameof(pitch), "NV12 pitch must be even, at least width, and plane offsets must fit Int32");
        if (y == IntPtr.Zero) throw new ArgumentNullException(nameof(y));
        if (uv == IntPtr.Zero) throw new ArgumentNullException(nameof(uv));
        Span<int> gray = stackalloc int[66 * 14];
        for (int oy = 23; oy < 37; oy++)
        {
            int sy = (int)((long)oy * height / 270);
            int yOffset = sy * pitch, uvOffset = (sy / 2) * pitch;
            for (int ox = 17; ox < 83; ox++)
            {
                int sx = (int)((long)ox * width / 480);
                int pair = (sx / 2) * 2;
                double luma = Marshal.ReadByte(y, yOffset + sx);
                double u = Marshal.ReadByte(uv, uvOffset + pair) - 128;
                double v = Marshal.ReadByte(uv, uvOffset + pair + 1) - 128;
                int r = Clamp(luma + 1.402 * v);
                int g = Clamp(luma - 0.344 * u - 0.714 * v);
                int b = Clamp(luma + 1.772 * u);
                gray[(oy - 23) * 66 + ox - 17] = Luma(r, g, b);
            }
        }
        return Score(gray);
    }

    private static byte Clamp(double value) => value < 0 ? (byte)0 : value > 255 ? (byte)255 : (byte)value;
    private static int Luma(int r, int g, int b) => (299 * r + 587 * g + 114 * b + 500) / 1000;

    private static double Score(ReadOnlySpan<int> gray)
    {
        double total = 0;
        int index = 0;
        for (int y = 1; y <= 12; y++)
            for (int x = 1; x <= 64; x++)
            {
                int surround = 0;
                for (int dy = -1; dy <= 1; dy++)
                    for (int dx = -1; dx <= 1; dx++)
                        surround += gray[(y + dy) * 66 + x + dx];
                double highPass = gray[y * 66 + x] - surround / 9.0;
                // Preserve reference row-major double accumulation; no vectorized reduction.
                total += highPass * Weights[index++];
            }
        return total / 1000.0;
    }
}
