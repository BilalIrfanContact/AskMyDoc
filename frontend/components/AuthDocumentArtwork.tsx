export default function AuthDocumentArtwork() {
  return (
    <div className="auth-document-art" aria-hidden="true">
      <div className="art-sheet art-sheet-back">
        <div className="art-back-heading">Document signals</div>
        <div className="art-bar-chart">
          <span /><span /><span /><span /><span />
        </div>
        <div className="art-back-lines">
          <span /><span /><span /><span /><span /><span />
        </div>
      </div>

      <div className="art-sheet art-sheet-front">
        <header className="art-page-header">
          <span>Ideas in context</span>
          <span>Chapter 1</span>
        </header>

        <div className="art-page-lead">
          <span /><span /><span /><span />
        </div>

        <div className="art-page-image">
          <svg viewBox="0 0 240 132" role="presentation">
            <rect width="240" height="132" fill="#d9d7cf" />
            <circle cx="184" cy="32" r="13" fill="#efede5" />
            <path d="M0 112 54 64l34 31 32-51 49 50 27-24 44 42v20H0Z" fill="#8c8d87" />
            <path d="m55 64 16 15 17 16 32-51 16 17" fill="none" stroke="#f5f2e9" strokeWidth="5" opacity=".72" />
            <path d="M0 117c45-10 75-8 111 1 43 10 82 8 129-4v18H0Z" fill="#73756f" opacity=".58" />
          </svg>
        </div>

        <div className="art-page-body">
          <span /><span /><span /><span /><span /><span /><span /><span />
        </div>

        <div className="art-page-foot">
          <span /><span />
        </div>
      </div>
    </div>
  );
}
