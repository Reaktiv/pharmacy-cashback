/** A small hand-rolled icon set (no external icon library — see CLAUDE.md
 * §9 on dependencies). Consistent 24x24 stroke style throughout so the
 * whole product reads as one system. */

type IconProps = { className?: string }

const base = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

export function IconGrid({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <rect x="3.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="13.5" y="3.5" width="7" height="7" rx="2" />
      <rect x="3.5" y="13.5" width="7" height="7" rx="2" />
      <rect x="13.5" y="13.5" width="7" height="7" rx="2" />
    </svg>
  )
}

export function IconBuilding({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M5 21V5a1 1 0 0 1 1-1h6a1 1 0 0 1 1 1v16" />
      <path d="M13 21v-9h5a1 1 0 0 1 1 1v8" />
      <path d="M8 7h.01M11 7h.01M8 10.5h.01M11 10.5h.01M8 14h.01M11 14h.01" strokeWidth="2.2" />
      <path d="M3 21h18" />
    </svg>
  )
}

export function IconUsers({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="9" cy="8" r="3.2" />
      <path d="M2.8 20c.6-3.2 3.1-5.2 6.2-5.2s5.6 2 6.2 5.2" />
      <path d="M15.5 5.2a3.2 3.2 0 0 1 0 6.2" />
      <path d="M16.8 14.9c2.6.5 4.5 2.3 5 5" />
    </svg>
  )
}

export function IconUser({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20c1.5-4 5-6 7.5-6s6 2 7.5 6" />
    </svg>
  )
}

export function IconMegaphone({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M3 10v4a1 1 0 0 0 1 1h2l1.2 4.2a1 1 0 0 0 1 .8H10l-1-5" />
      <path d="M6 10 17 4.5a1 1 0 0 1 1.4.9v13.2a1 1 0 0 1-1.4.9L6 14" />
      <path d="M18.4 8.3a3 3 0 0 1 0 5.4" />
    </svg>
  )
}

export function IconChartBar({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M4 20V10M10 20V4M16 20v-7M22 20H2" />
    </svg>
  )
}

export function IconLogout({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M10 8V6a2 2 0 0 1 2-2h7a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-7a2 2 0 0 1-2-2v-2" />
      <path d="M15 12H3l3-3" />
      <path d="M6 15l-3-3" />
    </svg>
  )
}

export function IconBot({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <rect x="4" y="8" width="16" height="11" rx="3" />
      <path d="M12 8V4" />
      <circle cx="12" cy="3" r="1.2" fill="currentColor" stroke="none" />
      <path d="M8.5 13.5v1M15.5 13.5v1" strokeWidth="2.2" />
      <path d="M9 17.2c1.9 1.1 4.1 1.1 6 0" />
      <path d="M2 12v3M22 12v3" />
    </svg>
  )
}

export function IconKey({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="M10.8 12.2 20 3" />
      <path d="M16.5 6.5 19 9M13.3 9.7l2.1 2.1" />
    </svg>
  )
}

export function IconWallet({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M3 8a2 2 0 0 1 2-2h13a1 1 0 0 1 1 1v2" />
      <rect x="3" y="6" width="18" height="14" rx="2" />
      <path d="M16 13.5h3a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1h-3a1.75 1.75 0 0 1 0-3.5Z" />
    </svg>
  )
}

export function IconPulse({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M3 12h3.5l2-6 4 12 2-9 1.5 3H21" />
    </svg>
  )
}

export function IconReceipt({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M6 3h12v17.2a.6.6 0 0 1-.92.5l-1.83-1.2-1.83 1.2a1 1 0 0 1-1.08 0l-1.84-1.2-1.83 1.2a1 1 0 0 1-1.08 0l-1.83-1.2A.6.6 0 0 1 6 20.2Z" />
      <path d="M9 8h6M9 11.5h6M9 15h3.5" />
    </svg>
  )
}

export function IconTrendUp({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M3 16.5 9.5 10l4 4L21 6" />
      <path d="M15.5 6H21v5.5" />
    </svg>
  )
}

export function IconTrendDown({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M3 7.5 9.5 14l4-4L21 18" />
      <path d="M15.5 18H21v-5.5" />
    </svg>
  )
}

export function IconScale({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M12 3v18M8 21h8" />
      <path d="M4 7h6M14 7h6" />
      <path d="m4 7-2.5 5a2.6 2.6 0 0 0 5 0Z" />
      <path d="m20 7-2.5 5a2.6 2.6 0 0 0 5 0Z" />
    </svg>
  )
}

export function IconAlertCircle({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M12 8v5" strokeWidth="2.2" />
      <path d="M12 16.2h.01" strokeWidth="2.6" />
    </svg>
  )
}

export function IconCheckCircle({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="9" />
      <path d="M8.5 12.3 11 14.8l4.8-5.6" />
    </svg>
  )
}

export function IconPlus({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M12 5v14M5 12h14" strokeWidth="2.1" />
    </svg>
  )
}

export function IconArrowLeft({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M19 12H5M11 6l-6 6 6 6" />
    </svg>
  )
}

export function IconChevronDown({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M6 9l6 6 6-6" />
    </svg>
  )
}

export function IconBold({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M6.5 4.5h6a3.2 3.2 0 0 1 0 6.4h-6Z" />
      <path d="M6.5 10.9h7a3.4 3.4 0 0 1 0 6.8h-7Z" />
    </svg>
  )
}

export function IconItalic({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M11 4.5h6M7 17.5h6M14 4.5l-4 13" />
    </svg>
  )
}

export function IconUnderline({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M6 4v6.5a4.8 4.8 0 0 0 9.6 0V4" />
      <path d="M5 19.5h11.5" />
    </svg>
  )
}

export function IconStrikethrough({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M6.2 6.2c.4-1.6 2.3-2.7 4.6-2.7 2.6 0 4.4 1.3 4.4 3" />
      <path d="M7.6 17.3c.6 1.6 2.3 2.5 4.4 2.5 2.6 0 4.7-1.1 4.7-3 0-1.2-.9-2.1-2.3-2.7" />
      <path d="M4 12h16" />
    </svg>
  )
}

export function IconCode({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M8.5 8 4.5 12l4 4M15.5 8l4 4-4 4" />
    </svg>
  )
}

export function IconLinkChain({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M9.5 14.5 14.5 9.5" />
      <path d="M11 7.5 13 5.6a3.4 3.4 0 0 1 4.9 4.9L15.9 12.5" />
      <path d="M13 16.5 11 18.4a3.4 3.4 0 0 1-4.9-4.9L8.1 11.5" />
    </svg>
  )
}

export function IconImagePicture({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <rect x="3.5" y="4.5" width="17" height="15" rx="2.5" />
      <circle cx="9" cy="10" r="1.6" />
      <path d="m5 17 4.8-4.8a2 2 0 0 1 2.8 0L15 14.6M14.5 14 16 12.5a2 2 0 0 1 2.8 0L21 14.7" />
    </svg>
  )
}

export function IconVideoCamera({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <rect x="3" y="6.5" width="12.5" height="11" rx="2.2" />
      <path d="M15.5 10.8 20 8v8l-4.5-2.8Z" />
    </svg>
  )
}

export function IconUploadCloud({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M7 17.5A4.5 4.5 0 0 1 7.8 8.6 5.5 5.5 0 0 1 18 10a3.8 3.8 0 0 1-1 7.5Z" />
      <path d="M12 20v-7.5M9.2 15.2 12 12.4l2.8 2.8" />
    </svg>
  )
}

export function IconMenu({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M4 6.5h16M4 12h16M4 17.5h16" />
    </svg>
  )
}

export function IconX({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M6 6l12 12M18 6 6 18" />
    </svg>
  )
}

export function IconTrash({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M4.5 6.5h15" />
      <path d="M9 6.5V5a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 5v1.5" />
      <path d="M6.5 6.5 7.3 19a2 2 0 0 0 2 1.9h5.4a2 2 0 0 0 2-1.9l.8-12.5" />
      <path d="M10.2 10.5v6M13.8 10.5v6" />
    </svg>
  )
}

export function IconAlertTriangle({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M10.6 4.2 2.9 18a1.8 1.8 0 0 0 1.6 2.7h15a1.8 1.8 0 0 0 1.6-2.7L13.4 4.2a1.8 1.8 0 0 0-2.8 0Z" />
      <path d="M12 9.8v4" strokeWidth="2.2" />
      <path d="M12 17.2h.01" strokeWidth="2.6" />
    </svg>
  )
}

export function IconSend({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M4.5 11 20 4l-6 15.5-3.3-6.2L4.5 11Z" />
      <path d="M10.7 13.3 20 4" />
    </svg>
  )
}

export function IconPhone({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <path d="M7.5 3h2.2l1.3 4.4-2 1.6a11.5 11.5 0 0 0 5.9 5.9l1.6-2 4.4 1.3v2.2c0 1.4-1.2 2.5-2.6 2.3A17.5 17.5 0 0 1 4.9 5.6c-.2-1.4.9-2.6 2.3-2.6Z" />
    </svg>
  )
}

export function IconCapsule({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <rect x="2.5" y="8.6" width="19" height="6.8" rx="3.4" transform="rotate(-35 12 12)" />
      <path d="M12 12 7.6 16.4" strokeWidth="1.6" />
    </svg>
  )
}

export function IconPillBottle({ className }: IconProps) {
  return (
    <svg viewBox="0 0 64 64" fill="none" className={className} aria-hidden="true">
      <rect x="16" y="18" width="32" height="38" rx="8" stroke="currentColor" strokeWidth="2.2" />
      <path d="M16 30h32" stroke="currentColor" strokeWidth="2.2" />
      <rect x="22" y="8" width="20" height="12" rx="4" stroke="currentColor" strokeWidth="2.2" />
      <path d="M25 40h6M33 40h6M25 46h14" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" />
    </svg>
  )
}

export function IconClipboardEmpty({ className }: IconProps) {
  return (
    <svg viewBox="0 0 64 64" fill="none" className={className} aria-hidden="true">
      <rect x="14" y="10" width="36" height="46" rx="6" stroke="currentColor" strokeWidth="2.2" />
      <rect x="24" y="6" width="16" height="9" rx="3" stroke="currentColor" strokeWidth="2.2" />
      <path
        d="M22 30h20M22 38h20M22 46h12"
        stroke="currentColor"
        strokeWidth="2.2"
        strokeLinecap="round"
        strokeDasharray="3 5"
      />
    </svg>
  )
}

export function IconCrossShield({ className }: IconProps) {
  return (
    <svg viewBox="0 0 64 64" fill="none" className={className} aria-hidden="true">
      <path
        d="M32 6 54 14v16c0 15-9.4 25.4-22 28-12.6-2.6-22-13-22-28V14Z"
        stroke="currentColor"
        strokeWidth="2.2"
      />
      <path d="M32 22v20M22 32h20" stroke="currentColor" strokeWidth="3.4" strokeLinecap="round" />
    </svg>
  )
}

export function IconSettings({ className }: IconProps) {
  return (
    <svg {...base} className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="2.8" />
      <path
        d="M19.4 14.5a1.6 1.6 0 0 0 .3 1.75l.06.06a1.9 1.9 0 1 1-2.7 2.7l-.06-.06a1.6 1.6 0 0 0-1.75-.3 1.6 1.6 0 0 0-1 1.46V20.3a1.9 1.9 0 0 1-3.8 0v-.1a1.6 1.6 0 0 0-1.05-1.42 1.6 1.6 0 0 0-1.75.3l-.06.06a1.9 1.9 0 1 1-2.7-2.7l.06-.06a1.6 1.6 0 0 0 .3-1.75 1.6 1.6 0 0 0-1.46-1H3.7a1.9 1.9 0 0 1 0-3.8h.1A1.6 1.6 0 0 0 5.2 8.5a1.6 1.6 0 0 0-.3-1.75l-.06-.06a1.9 1.9 0 1 1 2.7-2.7l.06.06a1.6 1.6 0 0 0 1.75.3H9.4a1.6 1.6 0 0 0 1-1.46V2.7a1.9 1.9 0 0 1 3.8 0v.1a1.6 1.6 0 0 0 1 1.46 1.6 1.6 0 0 0 1.75-.3l.06-.06a1.9 1.9 0 1 1 2.7 2.7l-.06.06a1.6 1.6 0 0 0-.3 1.75V8.5a1.6 1.6 0 0 0 1.46 1h.1a1.9 1.9 0 0 1 0 3.8h-.1a1.6 1.6 0 0 0-1.46 1z"
      />
    </svg>
  )
}
