/** Shrink a photo and read its QR in the browser. jsQR sees pixels, not a file. */

import jsQR from "jsqr";

export const LONG_EDGE = 3000;

export function fitSize(width, height) {
  const long = Math.max(width, height);
  if (long <= LONG_EDGE) return { width, height };
  const scale = LONG_EDGE / long;
  return {
    width: Math.max(1, Math.round(width * scale)),
    height: Math.max(1, Math.round(height * scale)),
  };
}

export function splitPayload(text) {
  if (!text || text.indexOf("#") <= 0 || text.indexOf("#") !== text.lastIndexOf("#")) return null;
  const mark = text.indexOf("#");
  const paperId = text.slice(0, mark);
  const pageText = text.slice(mark + 1);
  const page = Number(pageText);
  if (!paperId || !Number.isInteger(page) || page < 1 || String(page) !== pageText) return null;
  return { paperId, page };
}

export function decodeQr(rgba, width, height, reader = jsQR) {
  const hit = reader(rgba, width, height);
  if (hit && hit.data) return hit.data;
  const crop = topRight(rgba, width, height);
  if (!crop) return null;
  const again = reader(crop.data, crop.width, crop.height);
  return again && again.data ? again.data : null;
}

export async function preparePhoto(file) {
  const bitmap = await createOrientedBitmap(file);
  const fitted = fitSize(bitmap.width, bitmap.height);
  const canvas = document.createElement("canvas");
  canvas.width = fitted.width;
  canvas.height = fitted.height;
  const context = canvas.getContext("2d", { willReadFrequently: true });
  context.drawImage(bitmap, 0, 0, fitted.width, fitted.height);
  if (typeof bitmap.close === "function") bitmap.close();
  const frame = context.getImageData(0, 0, fitted.width, fitted.height);
  const payload = decodeQr(frame.data, fitted.width, fitted.height);
  const blob = await new Promise((resolve, reject) => {
    canvas.toBlob((value) => (value ? resolve(value) : reject(new Error("jpeg"))), "image/jpeg", 0.85);
  });
  return { payload: payload || "", blob, thumb: URL.createObjectURL(blob) };
}

function createOrientedBitmap(file) {
  try {
    return createImageBitmap(file, { imageOrientation: "from-image" });
  } catch (reason) {
    return createImageBitmap(file);
  }
}

function topRight(rgba, width, height) {
  if (width < 16 || height < 16) return null;
  const x0 = Math.floor(width * 0.55);
  const y1 = Math.floor(height * 0.45);
  const cropWidth = width - x0;
  const cropHeight = Math.max(1, y1);
  const cropped = new Uint8ClampedArray(cropWidth * cropHeight * 4);
  for (let y = 0; y < cropHeight; y += 1) {
    const from = ((y * width) + x0) * 4;
    cropped.set(rgba.subarray(from, from + cropWidth * 4), y * cropWidth * 4);
  }
  return scale2(cropped, cropWidth, cropHeight);
}

function scale2(data, width, height) {
  const outWidth = width * 2;
  const outHeight = height * 2;
  const out = new Uint8ClampedArray(outWidth * outHeight * 4);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const src = (y * width + x) * 4;
      for (let dy = 0; dy < 2; dy += 1) {
        for (let dx = 0; dx < 2; dx += 1) {
          const dst = ((y * 2 + dy) * outWidth + (x * 2 + dx)) * 4;
          out[dst] = data[src];
          out[dst + 1] = data[src + 1];
          out[dst + 2] = data[src + 2];
          out[dst + 3] = data[src + 3];
        }
      }
    }
  }
  return { data: out, width: outWidth, height: outHeight };
}
