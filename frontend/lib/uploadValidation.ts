const SUPPORTED_UPLOAD_EXTENSIONS = new Set([".pdf", ".md"]);
const SUPPORTED_UPLOAD_MIME_TYPES = new Set(["application/pdf", "text/markdown"]);

export const UPLOAD_FILE_ACCEPT = ".pdf,.md,text/markdown,application/pdf";

export function isSupportedUploadFile(file: Pick<File, "name" | "type">) {
  const normalizedType = file.type.toLowerCase();
  if (SUPPORTED_UPLOAD_MIME_TYPES.has(normalizedType)) {
    return true;
  }

  const normalizedName = file.name.toLowerCase();
  return Array.from(SUPPORTED_UPLOAD_EXTENSIONS).some((extension) => normalizedName.endsWith(extension));
}

export const MAX_UPLOAD_BYTES = 15_000_000;
export const SMALLER_FILE_MESSAGE = "Please select a smaller file. The maximum file size is 15 MB.";

export function getUploadValidationError(file: Pick<File, "name" | "type" | "size">): string | null {
  if (file.size > MAX_UPLOAD_BYTES) return SMALLER_FILE_MESSAGE;
  if (!isSupportedUploadFile(file)) return "Please select a valid PDF or Markdown file.";
  if (file.size === 0) return "Please select a file that is not empty.";
  return null;
}
