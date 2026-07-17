/// <reference types="@raycast/api">

/* 🚧 🚧 🚧
 * This file is auto-generated from the extension's manifest.
 * Do not modify manually. Instead, update the `package.json` file.
 * 🚧 🚧 🚧 */

/* eslint-disable @typescript-eslint/ban-types */

type ExtensionPreferences = {
  /** Job Search Folder - Private job-search repository root. Overrides CAREER_JOB_SEARCH_ROOT when set. */
  "jobSearchRoot"?: string
}

/** Preferences accessible in all the extension's commands */
declare type Preferences = ExtensionPreferences

declare namespace Preferences {
  /** Preferences accessible in the `job-new` command */
  export type JobNew = ExtensionPreferences & {}
  /** Preferences accessible in the `job-match` command */
  export type JobMatch = ExtensionPreferences & {}
  /** Preferences accessible in the `job-review` command */
  export type JobReview = ExtensionPreferences & {}
  /** Preferences accessible in the `job-log` command */
  export type JobLog = ExtensionPreferences & {}
  /** Preferences accessible in the `job-analytics` command */
  export type JobAnalytics = ExtensionPreferences & {}
  /** Preferences accessible in the `job-deadlines` command */
  export type JobDeadlines = ExtensionPreferences & {}
  /** Preferences accessible in the `job-rebuild-cvs` command */
  export type JobRebuildCvs = ExtensionPreferences & {}
  /** Preferences accessible in the `job-discover-opportunities` command */
  export type JobDiscoverOpportunities = ExtensionPreferences & {}
  /** Preferences accessible in the `job-daily-queue` command */
  export type JobDailyQueue = ExtensionPreferences & {}
  /** Preferences accessible in the `job-review-opportunities` command */
  export type JobReviewOpportunities = ExtensionPreferences & {}
  /** Preferences accessible in the `job-match-opportunities` command */
  export type JobMatchOpportunities = ExtensionPreferences & {}
}

declare namespace Arguments {
  /** Arguments passed to the `job-new` command */
  export type JobNew = {}
  /** Arguments passed to the `job-match` command */
  export type JobMatch = {}
  /** Arguments passed to the `job-review` command */
  export type JobReview = {}
  /** Arguments passed to the `job-log` command */
  export type JobLog = {}
  /** Arguments passed to the `job-analytics` command */
  export type JobAnalytics = {}
  /** Arguments passed to the `job-deadlines` command */
  export type JobDeadlines = {}
  /** Arguments passed to the `job-rebuild-cvs` command */
  export type JobRebuildCvs = {}
  /** Arguments passed to the `job-discover-opportunities` command */
  export type JobDiscoverOpportunities = {}
  /** Arguments passed to the `job-daily-queue` command */
  export type JobDailyQueue = {}
  /** Arguments passed to the `job-review-opportunities` command */
  export type JobReviewOpportunities = {}
  /** Arguments passed to the `job-match-opportunities` command */
  export type JobMatchOpportunities = {}
}

