"use client"

import * as React from "react"
import {
  ColumnDef,
  ColumnFiltersState,
  RowSelectionState,
  SortingState,
  VisibilityState,
  PaginationState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Search, Sparkles, Trash2, Loader2, LucideIcon } from "lucide-react"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  searchQuery: string
  onSearchChange: (value: string) => void
  onAnalyze?: (selectedItems: TData[]) => void
  onBulkDelete?: (selectedItems: TData[]) => void
  onRowClick?: (item: TData) => void
  isSearching?: boolean
  searchPlaceholder?: string
  emptyIcon?: LucideIcon
  emptyTitle?: string
  emptyDescription?: string
  totalCount?: number
  // Server-side mode
  serverSide?: boolean
  pageCount?: number
  currentPage?: number
  pageSize?: number
  onPageChange?: (page: number) => void
  onPageSizeChange?: (pageSize: number) => void
  onSortingChange?: (sorting: SortingState) => void
  // Controlled row selection
  rowSelection?: RowSelectionState
  onRowSelectionChange?: (selection: RowSelectionState) => void
}

export function DataTable<TData, TValue>({
  columns,
  data,
  searchQuery,
  onSearchChange,
  onAnalyze,
  onBulkDelete,
  onRowClick,
  isSearching = false,
  searchPlaceholder = "Search...",
  emptyIcon: EmptyIcon,
  emptyTitle = "No items found",
  emptyDescription = "Try adjusting your filters",
  totalCount,
  serverSide = false,
  pageCount: externalPageCount,
  currentPage = 1,
  pageSize: externalPageSize = 20,
  onPageChange,
  onPageSizeChange,
  onSortingChange: externalOnSortingChange,
  rowSelection: externalRowSelection,
  onRowSelectionChange: externalOnRowSelectionChange,
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>([])
  const [columnVisibility, setColumnVisibility] = React.useState<VisibilityState>({})
  const [internalRowSelection, setInternalRowSelection] = React.useState<RowSelectionState>({})

  const isRowSelectionControlled = externalRowSelection !== undefined
  const rowSelection = isRowSelectionControlled ? externalRowSelection : internalRowSelection

  const handleRowSelectionChange = React.useCallback(
    (updater: RowSelectionState | ((old: RowSelectionState) => RowSelectionState)) => {
      const newSelection = typeof updater === 'function' ? updater(rowSelection) : updater
      if (isRowSelectionControlled && externalOnRowSelectionChange) {
        externalOnRowSelectionChange(newSelection)
      } else {
        setInternalRowSelection(newSelection)
      }
    },
    [rowSelection, isRowSelectionControlled, externalOnRowSelectionChange]
  )

  const handleSortingChange = React.useCallback((updater: SortingState | ((old: SortingState) => SortingState)) => {
    const newSorting = typeof updater === 'function' ? updater(sorting) : updater
    setSorting(newSorting)
    if (serverSide && externalOnSortingChange) {
      externalOnSortingChange(newSorting)
    }
  }, [sorting, serverSide, externalOnSortingChange])

  const table = useReactTable({
    data,
    columns,
    onSortingChange: handleSortingChange,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    ...(!serverSide && {
      getPaginationRowModel: getPaginationRowModel(),
      getSortedRowModel: getSortedRowModel(),
      getFilteredRowModel: getFilteredRowModel(),
    }),
    ...(serverSide && {
      manualPagination: true,
      manualSorting: true,
      pageCount: externalPageCount ?? -1,
    }),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: handleRowSelectionChange,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
      ...(serverSide && {
        pagination: {
          pageIndex: currentPage - 1,
          pageSize: externalPageSize,
        },
      }),
    },
  })

  // Get selected rows as original data
  const selectedRows = table.getFilteredSelectedRowModel().rows.map(row => row.original)
  const selectedCount = selectedRows.length

  const clearRowSelection = () => {
    if (isRowSelectionControlled && externalOnRowSelectionChange) {
      externalOnRowSelectionChange({})
    } else {
      setInternalRowSelection({})
    }
  }

  const handleAnalyze = () => {
    if (onAnalyze && selectedCount > 0) {
      onAnalyze(selectedRows)
      clearRowSelection()
    }
  }

  const handleBulkDelete = () => {
    if (onBulkDelete && selectedCount > 0) {
      onBulkDelete(selectedRows)
      clearRowSelection()
    }
  }

  const displayCount = totalCount ?? data.length
  const effectivePageCount = serverSide
    ? (externalPageCount ?? 1)
    : table.getPageCount()
  const effectivePageIndex = serverSide
    ? currentPage - 1
    : table.getState().pagination.pageIndex
  const effectivePageSize = serverSide
    ? externalPageSize
    : table.getState().pagination.pageSize

  const canPreviousPage = serverSide
    ? currentPage > 1
    : table.getCanPreviousPage()
  const canNextPage = serverSide
    ? currentPage < (externalPageCount ?? 1)
    : table.getCanNextPage()

  const handlePrevious = () => {
    if (serverSide && onPageChange) {
      onPageChange(currentPage - 1)
    } else {
      table.previousPage()
    }
  }

  const handleNext = () => {
    if (serverSide && onPageChange) {
      onPageChange(currentPage + 1)
    } else {
      table.nextPage()
    }
  }

  const handlePageSizeChange = (value: string) => {
    const size = Number(value)
    if (serverSide && onPageSizeChange) {
      onPageSizeChange(size)
    } else {
      table.setPageSize(size)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <div className="relative flex-1 max-w-sm">
          {isSearching ? (
            <Loader2 className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4 animate-spin" />
          ) : (
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-muted-foreground h-4 w-4" />
          )}
          <Input
            placeholder={searchPlaceholder}
            value={searchQuery}
            onChange={(event) => onSearchChange(event.target.value)}
            className="pl-10"
          />
        </div>
        <div className="text-sm text-muted-foreground">
          {isSearching ? (
            <span className="flex items-center gap-2">
              <Loader2 className="h-3 w-3 animate-spin" />
              Searching...
            </span>
          ) : (
            `Showing ${displayCount} items`
          )}
        </div>
      </div>

      {/* Action buttons when items are selected */}
      {selectedCount > 0 && (
        <div className="flex items-center justify-between bg-muted/50 rounded-lg p-4 border border-border">
          <div className="text-sm font-medium">
            <span className="font-bold text-foreground">{selectedCount}</span> item{selectedCount !== 1 ? 's' : ''} selected
          </div>
          <div className="flex items-center gap-3">
            {onAnalyze && (
              <Button
                onClick={handleAnalyze}
                variant="default"
                size="sm"
                className="flex items-center gap-2"
              >
                <Sparkles className="w-4 h-4" />
                <span>Re-analyze ({selectedCount})</span>
              </Button>
            )}
            {onBulkDelete && (
              <Button
                onClick={handleBulkDelete}
                variant="outline"
                size="sm"
                className="flex items-center gap-2 text-destructive hover:bg-destructive/10 border-destructive/30"
              >
                <Trash2 className="w-4 h-4" />
                <span>Delete ({selectedCount})</span>
              </Button>
            )}
          </div>
        </div>
      )}

      <div className="rounded-md border-border" style={{ border: '1px solid hsl(var(--border))' }}>
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((headerGroup) => (
              <TableRow key={headerGroup.id} className="bg-muted/50">
                {headerGroup.headers.map((header) => {
                  return (
                    <TableHead key={header.id}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(
                            header.column.columnDef.header,
                            header.getContext()
                          )}
                    </TableHead>
                  )
                })}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows?.length ? (
              table.getRowModel().rows.map((row) => (
                <TableRow
                  key={row.id}
                  data-state={row.getIsSelected() && "selected"}
                  onClick={(e) => {
                    const target = e.target as HTMLElement;
                    if (target.closest('button') || target.closest('input[type="checkbox"]') || target.closest('[role="checkbox"]')) {
                      return;
                    }
                    if (onRowClick) {
                      onRowClick(row.original);
                    }
                  }}
                  className={onRowClick ? "cursor-pointer hover:bg-muted/50" : ""}
                >
                  {row.getVisibleCells().map((cell) => (
                    <TableCell key={cell.id}>
                      {flexRender(
                        cell.column.columnDef.cell,
                        cell.getContext()
                      )}
                    </TableCell>
                  ))}
                </TableRow>
              ))
            ) : (
              <TableRow>
                <TableCell
                  colSpan={columns.length}
                  className="h-32 text-center"
                >
                  <div className="flex flex-col items-center justify-center py-8">
                    {EmptyIcon && <EmptyIcon className="w-16 h-16 mb-4 text-muted-foreground opacity-30" />}
                    <p className="text-foreground font-semibold text-lg">
                      {emptyTitle}
                    </p>
                    <p className="text-muted-foreground text-sm mt-2">
                      {emptyDescription}
                    </p>
                  </div>
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </div>

      <div className="flex items-center justify-between px-2">
        <div className="flex-1 text-sm text-muted-foreground">
          {table.getFilteredSelectedRowModel().rows.length} of{" "}
          {data.length} row(s) selected.
        </div>
        <div className="flex items-center space-x-6 lg:space-x-8">
          <div className="flex items-center space-x-2">
            <p className="text-sm font-medium">Rows per page</p>
            <Select
              value={String(effectivePageSize)}
              onValueChange={handlePageSizeChange}
            >
              <SelectTrigger className="h-8 w-[70px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[10, 20, 30, 40, 50].map((pageSize) => (
                  <SelectItem key={pageSize} value={String(pageSize)}>
                    {pageSize}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <div className="flex w-[100px] items-center justify-center text-sm font-medium">
            Page {effectivePageIndex + 1} of{" "}
            {effectivePageCount}
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handlePrevious}
              disabled={!canPreviousPage}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={handleNext}
              disabled={!canNextPage}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
