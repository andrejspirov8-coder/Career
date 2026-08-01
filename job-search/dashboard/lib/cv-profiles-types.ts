export interface VariantProfile {
  name: string
  language: string
  focus: string
  display_order: number
  pdf_stem: string
  markdown: string
  target_titles: string[]
  keywords: string[]
  negative_keywords: string[]
}

export interface VariantProfilesConfig {
  variants: Record<string, VariantProfile>
}
