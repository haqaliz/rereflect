"use client"

import { Skeleton } from "@/components/ui/skeleton"

// Skeleton for Dashboard page
export function DashboardSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Header skeleton */}
        <div className="mb-8 flex justify-between items-start">
          <div>
            <Skeleton className="h-10 w-48 mb-2" />
            <Skeleton className="h-5 w-80" />
          </div>
          <Skeleton className="h-9 w-32" />
        </div>

        {/* Stat cards skeleton */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="p-6 rounded-2xl border border-border bg-card">
              <div className="flex items-start justify-between">
                <div className="flex-1">
                  <Skeleton className="h-4 w-24 mb-3" />
                  <Skeleton className="h-10 w-16" />
                </div>
                <Skeleton className="h-14 w-14 rounded-2xl" />
              </div>
            </div>
          ))}
        </div>

        {/* Charts skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-8">
          <div className="p-6 rounded-2xl border border-border bg-card">
            <div className="flex items-center gap-3 mb-6">
              <Skeleton className="h-10 w-10 rounded-xl" />
              <div>
                <Skeleton className="h-5 w-40 mb-1" />
                <Skeleton className="h-4 w-48" />
              </div>
            </div>
            <div className="flex items-center gap-8">
              <Skeleton className="h-48 w-48 rounded-full" />
              <div className="flex-1 space-y-4">
                {[...Array(3)].map((_, i) => (
                  <div key={i} className="flex justify-between items-center">
                    <Skeleton className="h-4 w-20" />
                    <Skeleton className="h-6 w-10 rounded-full" />
                  </div>
                ))}
              </div>
            </div>
          </div>
          <div className="p-6 rounded-2xl border border-border bg-card">
            <div className="flex items-center gap-3 mb-6">
              <Skeleton className="h-10 w-10 rounded-xl" />
              <div>
                <Skeleton className="h-5 w-44 mb-1" />
                <Skeleton className="h-4 w-36" />
              </div>
            </div>
            <Skeleton className="h-48 w-full" />
          </div>
        </div>

        {/* Lists skeleton */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {[...Array(2)].map((_, i) => (
            <div key={i} className="p-6 rounded-2xl border border-border bg-card">
              <div className="flex justify-between items-center mb-6">
                <div className="flex items-center gap-3">
                  <Skeleton className="h-10 w-10 rounded-xl" />
                  <div>
                    <Skeleton className="h-5 w-28 mb-1" />
                    <Skeleton className="h-4 w-32" />
                  </div>
                </div>
                <Skeleton className="h-4 w-16" />
              </div>
              <div className="space-y-3">
                {[...Array(3)].map((_, j) => (
                  <div key={j} className="flex justify-between items-center p-3 rounded-lg bg-muted/50">
                    <div className="flex items-center gap-3">
                      <Skeleton className="h-5 w-5 rounded" />
                      <Skeleton className="h-4 w-32" />
                    </div>
                    <Skeleton className="h-6 w-8 rounded-full" />
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </main>
    </div>
  )
}

// Skeleton for DataTable pages (Feedbacks, Pain Points, Feature Requests, Urgent, Categories)
export function DataTablePageSkeleton({
  showFilters = false,
}: {
  showFilters?: boolean
}) {
  return (
    <div className="min-h-screen bg-background">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Page Header skeleton */}
        <div>
          <div className="flex items-center space-x-3 mb-2">
            <Skeleton className="h-14 w-14 rounded-xl" />
            <div>
              <Skeleton className="h-10 w-64 mb-2" />
              <Skeleton className="h-5 w-80" />
            </div>
          </div>
        </div>

        {/* Filters skeleton (optional) */}
        {showFilters && (
          <div className="p-6 rounded-2xl border border-border bg-card">
            <Skeleton className="h-4 w-16 mb-4" />
            <div className="flex flex-wrap gap-4">
              <Skeleton className="h-10 w-[180px]" />
              <Skeleton className="h-10 w-[180px]" />
            </div>
          </div>
        )}

        {/* DataTable skeleton */}
        <div className="p-6 rounded-2xl border border-border bg-card">
          {/* Search bar skeleton */}
          <div className="flex items-center justify-between mb-4">
            <Skeleton className="h-10 w-80" />
            <Skeleton className="h-4 w-32" />
          </div>

          {/* Table skeleton */}
          <div className="rounded-md border border-border">
            {/* Table header */}
            <div className="bg-muted/50 p-4 border-b border-border">
              <div className="flex items-center gap-4">
                <Skeleton className="h-4 w-4" />
                <Skeleton className="h-4 w-12" />
                <Skeleton className="h-4 w-32 flex-1" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-16" />
              </div>
            </div>

            {/* Table rows */}
            {[...Array(5)].map((_, i) => (
              <div key={i} className="p-4 border-b border-border last:border-b-0">
                <div className="flex items-center gap-4">
                  <Skeleton className="h-4 w-4" />
                  <Skeleton className="h-4 w-10" />
                  <div className="flex-1 flex items-start gap-3">
                    <Skeleton className="h-8 w-8 rounded-lg flex-shrink-0" />
                    <div className="flex-1">
                      <Skeleton className="h-4 w-full max-w-md mb-2" />
                      <Skeleton className="h-4 w-3/4 max-w-sm" />
                    </div>
                  </div>
                  <Skeleton className="h-6 w-20 rounded-full" />
                  <div className="flex gap-1">
                    <Skeleton className="h-6 w-16 rounded-full" />
                    <Skeleton className="h-6 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-4 w-20" />
                  <Skeleton className="h-6 w-16 rounded-full" />
                </div>
              </div>
            ))}
          </div>

          {/* Pagination skeleton */}
          <div className="flex items-center justify-between mt-4 px-2">
            <Skeleton className="h-4 w-40" />
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-16" />
              </div>
              <Skeleton className="h-4 w-24" />
              <div className="flex gap-2">
                <Skeleton className="h-8 w-20" />
                <Skeleton className="h-8 w-16" />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

// Skeleton for Feedbacks page (with filters and action buttons)
export function FeedbacksPageSkeleton() {
  return (
    <div className="min-h-screen bg-background">
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Page Title and Actions */}
        <div className="mb-8 flex justify-between items-start">
          <div>
            <Skeleton className="h-10 w-40 mb-2" />
            <Skeleton className="h-5 w-72" />
          </div>
          <div className="flex gap-3">
            <Skeleton className="h-10 w-32" />
            <Skeleton className="h-10 w-36" />
          </div>
        </div>

        {/* Filters */}
        <div className="mb-6 p-6 rounded-2xl border border-border bg-card">
          <Skeleton className="h-4 w-16 mb-4" />
          <div className="flex flex-wrap gap-4">
            <Skeleton className="h-10 w-[180px]" />
            <Skeleton className="h-10 w-[180px]" />
          </div>
        </div>

        {/* DataTable */}
        <div className="p-6 rounded-2xl border border-border bg-card">
          {/* Search bar */}
          <div className="flex items-center justify-between mb-4">
            <Skeleton className="h-10 w-80" />
            <Skeleton className="h-4 w-32" />
          </div>

          {/* Table */}
          <div className="rounded-md border border-border">
            <div className="bg-muted/50 p-4 border-b border-border">
              <div className="flex items-center gap-4">
                <Skeleton className="h-4 w-4" />
                <Skeleton className="h-4 w-12" />
                <Skeleton className="h-4 w-32 flex-1" />
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-4 w-20" />
                <Skeleton className="h-4 w-16" />
                <Skeleton className="h-4 w-16" />
              </div>
            </div>

            {[...Array(5)].map((_, i) => (
              <div key={i} className="p-4 border-b border-border last:border-b-0">
                <div className="flex items-center gap-4">
                  <Skeleton className="h-4 w-4" />
                  <Skeleton className="h-4 w-10" />
                  <Skeleton className="h-4 w-full max-w-md flex-1" />
                  <Skeleton className="h-6 w-20 rounded-full" />
                  <div className="flex gap-1">
                    <Skeleton className="h-6 w-16 rounded-full" />
                  </div>
                  <Skeleton className="h-6 w-16 rounded-full" />
                  <div className="flex gap-1">
                    <Skeleton className="h-8 w-8 rounded" />
                    <Skeleton className="h-8 w-8 rounded" />
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4 px-2">
            <Skeleton className="h-4 w-40" />
            <div className="flex items-center gap-6">
              <div className="flex items-center gap-2">
                <Skeleton className="h-4 w-24" />
                <Skeleton className="h-8 w-16" />
              </div>
              <Skeleton className="h-4 w-24" />
              <div className="flex gap-2">
                <Skeleton className="h-8 w-20" />
                <Skeleton className="h-8 w-16" />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
