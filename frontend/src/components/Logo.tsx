/** The brand mark: a rounded square carrying a medical cross with a pulse
 * line through it — reads as "pharmacy" without leaning on a literal pill
 * icon. Falls back to this generic mark whenever no custom logo is set;
 * once one is (a tenant's own logo for tenant-scoped roles, or the
 * superadmin's platform logo — see Layout.tsx/LoginPage.tsx for which is
 * passed in), that image replaces it everywhere the brand appears. */
function BrandMark({ logoUrl }: { logoUrl?: string | null }) {
  return (
    <span className={`brand-mark${logoUrl ? ' has-image' : ''}`} aria-hidden="true">
      {logoUrl ? (
        <img src={logoUrl} alt="" className="brand-mark-img" />
      ) : (
        <svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path
            d="M12 4v6.5M12 13.5V20M4 12h6.5M13.5 12H20"
            stroke="white"
            strokeWidth="2.6"
            strokeLinecap="round"
          />
        </svg>
      )}
    </span>
  )
}

export default function Brand({
  subtitle,
  name = 'Pharmacy Cashback',
  logoUrl,
}: {
  subtitle?: string
  name?: string
  logoUrl?: string | null
}) {
  return (
    <div className="brand">
      <BrandMark logoUrl={logoUrl} />
      <span className="brand-name">
        {name}
        {subtitle && <small>{subtitle}</small>}
      </span>
    </div>
  )
}
