/** The brand mark: a rounded square carrying a medical cross with a pulse
 * line through it — reads as "pharmacy" without leaning on a literal pill
 * icon. Reused everywhere the brand appears (sidebar, every auth screen)
 * so the product reads as one system. */
function BrandMark() {
  return (
    <span className="brand-mark" aria-hidden="true">
      <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path
          d="M12 4v6.5M12 13.5V20M4 12h6.5M13.5 12H20"
          stroke="white"
          strokeWidth="2.6"
          strokeLinecap="round"
        />
      </svg>
    </span>
  )
}

export default function Brand({ subtitle }: { subtitle?: string }) {
  return (
    <div className="brand">
      <BrandMark />
      <span className="brand-name">
        Pharmacy Cashback
        {subtitle && <small>{subtitle}</small>}
      </span>
    </div>
  )
}
