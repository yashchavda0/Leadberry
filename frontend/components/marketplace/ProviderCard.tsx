"use client";

import Icon from "@/components/Icon";
import ProviderLogo from "@/components/ProviderLogo";
import { type MarketplaceProvider } from "@/lib/crm";

const categories: Record<string, string> = { marketplace: "Marketplace", social: "Social", commerce: "Commerce", form: "Forms", api: "API", telephony: "Telephony" };

export default function ProviderCard({ provider, connected, canAdd, onAdd }: { provider: MarketplaceProvider; connected: number; canAdd: boolean; onAdd: () => void }) {
  return <article className="provider-card">
    <div className="provider-card-top">
      <span className="provider-logo">
        <ProviderLogo code={provider.code} name={provider.name} />
        {connected > 0 && <span className="provider-connected" title={`${connected} connected`} aria-label={`${connected} connected`}>{connected}</span>}
      </span>
      <span className="provider-category">{categories[provider.category] || provider.category}</span>
    </div>
    <div className="provider-card-body">
      <h3>{provider.name}</h3>
      <p className="small muted">{provider.method}</p>
    </div>
    <div className="provider-card-footer">
      {provider.setup
        ? <button className="btn btn-primary provider-add" disabled={!canAdd} onClick={onAdd}><Icon name="plus" />Add connection</button>
        : <button className="btn provider-add" disabled>Unavailable</button>}
      {provider.documentation_url && <a className="btn icon-btn" href={provider.documentation_url} target="_blank" rel="noreferrer" aria-label={`${provider.name} documentation`} title="Documentation"><Icon name="external" /></a>}
    </div>
  </article>;
}
