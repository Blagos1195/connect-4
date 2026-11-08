const BOOK_VERSION_URL = "book-version.json?v=1";

async function fetchLatestBookVersion() {
  try {
    const response = await fetch(BOOK_VERSION_URL, { cache: "no-store" });
    if (!response.ok) throw new Error("Book version check failed.");
    const data = await response.json();
    if (Number.isInteger(data.version) && data.version > 0) return data.version;
  } catch {}
  return 1;
}

self.onmessage = async () => {
  try {
    const version = await fetchLatestBookVersion();
    const response = await fetch("7x6_small.book.gz?v=" + version);
    if (!response.ok) throw new Error("Could not download the opening book.");
    const data = await response.arrayBuffer();
    self.postMessage({ type: "downloaded", data, version }, [data]);
  } catch (error) {
    self.postMessage({ type: "error", message: error?.message || String(error) });
  }
};
