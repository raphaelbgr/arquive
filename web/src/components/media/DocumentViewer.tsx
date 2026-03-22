// TODO: Replace with pdfjs-dist for full inline rendering

import { useState, useCallback } from 'react';

interface DocumentViewerProps {
  src: string;
  pageCount?: number;
}

export function DocumentViewer({ src, pageCount = 1 }: DocumentViewerProps) {
  const [currentPage, setCurrentPage] = useState(1);

  const goToPrevPage = useCallback(() => {
    setCurrentPage((p) => Math.max(1, p - 1));
  }, []);

  const goToNextPage = useCallback(() => {
    setCurrentPage((p) => Math.min(pageCount, p + 1));
  }, [pageCount]);

  // Append page parameter for PDF viewers that support it
  const pdfUrl = `${src}#page=${currentPage}`;

  return (
    <div className="flex h-full w-full flex-col font-[Inter]">
      {/* PDF iframe */}
      <div className="flex-1 overflow-hidden">
        <iframe
          src={pdfUrl}
          className="h-full w-full border-0 bg-white"
          title="PDF Document Viewer"
        />
      </div>

      {/* Page navigation controls */}
      {pageCount > 1 && (
        <div className="flex items-center justify-center gap-3 bg-white/10 px-4 py-3 backdrop-blur-xl">
          <button
            onClick={goToPrevPage}
            disabled={currentPage <= 1}
            className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Previous page"
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z" />
            </svg>
          </button>

          <span className="min-w-[80px] text-center text-sm text-white/80">
            {currentPage} / {pageCount}
          </span>

          <button
            onClick={goToNextPage}
            disabled={currentPage >= pageCount}
            className="flex h-8 w-8 items-center justify-center rounded-full text-white transition-colors hover:bg-white/20 disabled:cursor-not-allowed disabled:opacity-30"
            aria-label="Next page"
          >
            <svg className="h-4 w-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z" />
            </svg>
          </button>
        </div>
      )}
    </div>
  );
}
