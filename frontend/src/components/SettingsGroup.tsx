import type { ReactNode } from 'react'

/** One settings section: a title/description header plus one or more
 * bodies (each a child form/block), divided internally by hairlines
 * instead of being re-wrapped in their own floating cards. */
export default function SettingsGroup({
  title,
  description,
  children,
}: {
  title: ReactNode
  description?: ReactNode
  children: ReactNode
}) {
  return (
    <section className="settings-group">
      <div className="settings-group-head">
        <h3>{title}</h3>
        {description && <p>{description}</p>}
      </div>
      {children}
    </section>
  )
}

export function SettingsGroupBody({ children }: { children: ReactNode }) {
  return <div className="settings-group-body">{children}</div>
}
