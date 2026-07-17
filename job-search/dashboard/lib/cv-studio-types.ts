export type CvSourceVersion = {
  version_id: string
  created_at: string
  reason: 'before_save' | 'before_restore' | string
  content_hash: string
  character_count: number
  word_count: number
}

export type CvStudioDocument = {
  schema: 'career_cv_studio_v1'
  variant: string
  source_filename: string
  content: string
  content_hash: string
  source_updated_at: string | null
  versions: CvSourceVersion[]
}

export type CvStudioBuildFile = {
  filename: string
  size_bytes: number
  updated_at: string | null
}

export type CvStudioBuild = {
  variant: string
  visual_pdf: CvStudioBuildFile
  ats_pdf: CvStudioBuildFile
  canva_text: CvStudioBuildFile
}

export type CvStudioMutationResult = {
  changed: boolean
  saved_version?: CvSourceVersion | null
  restored_version?: string
  document: CvStudioDocument
  build: CvStudioBuild
}

export type CvJobComparison = {
  schema: 'career_cv_job_comparison_v1'
  variant: string
  opportunity: {
    opportunity_id: string
    title: string
    company: string
    location: string
  }
  score: number
  tie_break_score: number
  rank: number
  variant_count: number
  keyword_hits: string[]
  negative_hits: string[]
  keyword_gaps: Array<{ keyword: string; count: number }>
  gap_notes: string[]
  recommended_variant: string
  is_recommended: boolean
  confidence: string
}

export type CvEditorPart = {
  id: string
  title: string
  heading: string | null
  content: string
}
