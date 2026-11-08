import { landingPages } from "@/lib/crm";
import { Field } from "./Ui";

export default function LandingPagePicker({ value }: { value?: string | null }) {
  return <Field label="Landing page"><select className="select" name="landing_page" aria-label="Landing page" defaultValue={value || ""}>
    <option value="">Automatic (first accessible page)</option>
    {landingPages.map(page => <option key={page.path} value={page.path}>{page.label}</option>)}
  </select><span className="small muted">The user must have access to this page. Saving validates the selected roles and overrides.</span></Field>;
}
