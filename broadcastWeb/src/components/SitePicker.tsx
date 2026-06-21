import type { PreviewResult } from "../models/broadcastModels";

interface Props {
  preview: PreviewResult;
  selected: Set<string>;
  onToggle: (siteKey: string) => void;
  disabled: boolean;
}

export default function SitePicker({ preview, selected, onToggle, disabled }: Props) {
  return (
    <>
      <p className="section-note">
        Eligible calendars are checked — uncheck any you don't want. Excluded
        calendars show why routing skipped them.
      </p>
      <ul className="site-list">
        {preview.eligible.map((site) => (
          <li key={site.site_key}>
            <input
              id={`site-${site.site_key}`}
              type="checkbox"
              checked={selected.has(site.site_key)}
              onChange={() => onToggle(site.site_key)}
              disabled={disabled}
            />
            <label className="site-name" htmlFor={`site-${site.site_key}`}>
              {site.name}
            </label>
          </li>
        ))}
        {preview.excluded.map((site) => (
          <li key={site.site_key} className="excluded">
            <input type="checkbox" checked={false} disabled readOnly />
            <span className="site-name">{site.site_key}</span>
            <span className="reason">— {site.reason}</span>
          </li>
        ))}
      </ul>
    </>
  );
}
