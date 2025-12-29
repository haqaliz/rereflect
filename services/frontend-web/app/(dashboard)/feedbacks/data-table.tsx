"use client"

import * as React from "react"
import {
  ColumnDef,
  ColumnFiltersState,
  SortingState,
  VisibilityState,
  flexRender,
  getCoreRowModel,
  getFilteredRowModel,
  getPaginationRowModel,
  getSortedRowModel,
  useReactTable,
} from "@tanstack/react-table"
import { useRouter } from "next/navigation"

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
import { Search, MessageSquare, Sparkles, Trash2, Loader2 } from "lucide-react"

interface DataTableProps<TData, TValue> {
  columns: ColumnDef<TData, TValue>[]
  data: TData[]
  searchQuery: string
  onSearchChange: (value: string) => void
  onAnalyze?: (selectedItems: TData[]) => void
  onBulkDelete?: (selectedItems: TData[]) => void
  onRowClick?: (item: TData) => void
  isSearching?: boolean
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
}: DataTableProps<TData, TValue>) {
  const [sorting, setSorting] = React.useState<SortingState>([])
  const [columnFilters, setColumnFilters] = React.useState<ColumnFiltersState>(
    []
  )
  const [columnVisibility, setColumnVisibility] =
    React.useState<VisibilityState>({})
  const [rowSelection, setRowSelection] = React.useState({})

  const table = useReactTable({
    data,
    columns,
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    getCoreRowModel: getCoreRowModel(),
    getPaginationRowModel: getPaginationRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
    onColumnVisibilityChange: setColumnVisibility,
    onRowSelectionChange: setRowSelection,
    state: {
      sorting,
      columnFilters,
      columnVisibility,
      rowSelection,
    },
  })

  // Get selected rows as original data
  const selectedRows = table.getFilteredSelectedRowModel().rows.map(row => row.original)
  const selectedCount = selectedRows.length

  const handleAnalyze = () => {
    if (onAnalyze && selectedCount > 0) {
      onAnalyze(selectedRows)
      // Clear selection after action
      setRowSelection({})
    }
  }

  const handleBulkDelete = () => {
    if (onBulkDelete && selectedCount > 0) {
      onBulkDelete(selectedRows)
      // Clear selection after action
      setRowSelection({})
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
            placeholder="Search feedback text or issues..."
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
            `Showing ${data.length} items`
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
                    // Don't navigate if clicking on checkbox or action buttons
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
                    <MessageSquare className="w-16 h-16 mb-4 text-muted-foreground opacity-30" />
                    <p className="text-foreground font-semibold text-lg">
                      No feedback found
                    </p>
                    <p className="text-muted-foreground text-sm mt-2">
                      Try adjusting your filters or add new feedback
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
          {table.getFilteredRowModel().rows.length} row(s) selected.
        </div>
        <div className="flex items-center space-x-6 lg:space-x-8">
          <div className="flex items-center space-x-2">
            <p className="text-sm font-medium">Rows per page</p>
            <select
              value={table.getState().pagination.pageSize}
              onChange={(e) => {
                table.setPageSize(Number(e.target.value))
              }}
              className="h-8 w-[70px] rounded-md border border-input bg-background px-2 text-sm"
            >
              {[10, 20, 30, 40, 50].map((pageSize) => (
                <option key={pageSize} value={pageSize}>
                  {pageSize}
                </option>
              ))}
            </select>
          </div>
          <div className="flex w-[100px] items-center justify-center text-sm font-medium">
            Page {table.getState().pagination.pageIndex + 1} of{" "}
            {table.getPageCount()}
          </div>
          <div className="flex items-center space-x-2">
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.previousPage()}
              disabled={!table.getCanPreviousPage()}
            >
              Previous
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => table.nextPage()}
              disabled={!table.getCanNextPage()}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
