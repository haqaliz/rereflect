"use client"

import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  AlertTriangle,
  ArrowUpDown,
  ShieldAlert,
  DatabaseZap,
  CreditCard,
  ServerCrash,
  KeyRound,
  CircleX,
  Gauge,
  MousePointerClick,
  Laptop,
  PackageX,
  FileQuestion,
  Paintbrush
} from "lucide-react"
import Link from "next/link"
import { FeedbackItem } from "@/lib/api/feedback"
import {
  getPainPointLabel,
  getPainPointColor,
  getCategoryBadgeStyle,
  getTagStyles
} from "@/lib/category-utils"

const getCategoryIcon = (category: string) => {
  const iconMap: Record<string, React.ReactNode> = {
    'security_breach': <ShieldAlert className="w-3.5 h-3.5" />,
    'data_loss': <DatabaseZap className="w-3.5 h-3.5" />,
    'payment_issue': <CreditCard className="w-3.5 h-3.5" />,
    'system_crash': <ServerCrash className="w-3.5 h-3.5" />,
    'authentication': <KeyRound className="w-3.5 h-3.5" />,
    'functionality_broken': <CircleX className="w-3.5 h-3.5" />,
    'performance': <Gauge className="w-3.5 h-3.5" />,
    'usability': <MousePointerClick className="w-3.5 h-3.5" />,
    'compatibility': <Laptop className="w-3.5 h-3.5" />,
    'missing_feature': <PackageX className="w-3.5 h-3.5" />,
    'documentation': <FileQuestion className="w-3.5 h-3.5" />,
    'cosmetic': <Paintbrush className="w-3.5 h-3.5" />,
  }
  return iconMap[category] || <AlertTriangle className="w-3.5 h-3.5" />
}

export const createColumns = (): ColumnDef<FeedbackItem>[] => [
  {
    id: "select",
    header: ({ table }) => (
      <Checkbox
        checked={
          table.getIsAllPageRowsSelected() ||
          (table.getIsSomePageRowsSelected() && "indeterminate")
        }
        onCheckedChange={(value) => table.toggleAllPageRowsSelected(!!value)}
        aria-label="Select all"
      />
    ),
    cell: ({ row }) => (
      <Checkbox
        checked={row.getIsSelected()}
        onCheckedChange={(value) => row.toggleSelected(!!value)}
        aria-label="Select row"
      />
    ),
    enableSorting: false,
    enableHiding: false,
  },
  {
    accessorKey: "id",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          ID
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => (
      <div className="font-bold font-mono text-muted-foreground">
        #{row.getValue("id")}
      </div>
    ),
  },
  {
    accessorKey: "text",
    header: "Feedback Text",
    cell: ({ row }) => {
      const text = row.getValue("text") as string
      const isUrgent = row.original.is_urgent
      return (
        <div className="max-w-md">
          <div className="flex items-start space-x-3">
            <div className="flex-shrink-0 mt-1">
              <div className="p-2 rounded-lg bg-secondary">
                <AlertTriangle className="w-4 h-4 text-primary" />
              </div>
            </div>
            <div className="flex-1">
              <p className="line-clamp-2 leading-relaxed">{text}</p>
              {isUrgent && (
                <Badge variant="destructive" className="mt-2">URGENT</Badge>
              )}
            </div>
          </div>
        </div>
      )
    },
  },
  {
    accessorKey: "pain_point_category",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Category
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => {
      const category = row.getValue("pain_point_category") as string | null
      const severity = row.original.pain_point_severity

      if (!category) {
        return <span className="text-xs text-muted-foreground italic">Uncategorized</span>
      }

      const categoryColor = getPainPointColor(category)
      const categoryStyle = getCategoryBadgeStyle(categoryColor)

      return (
        <div className="flex flex-col gap-1.5">
          <Badge
            variant="outline"
            className="flex items-center gap-1.5 w-fit transition-all hover:scale-105"
            style={categoryStyle}
          >
            {getCategoryIcon(category)}
            {getPainPointLabel(category)}
          </Badge>
          <span className="text-xs capitalize" style={{ color: categoryColor }}>
            {severity || 'moderate'}
          </span>
        </div>
      )
    },
  },
  {
    accessorKey: "tags",
    header: "Tags",
    cell: ({ row }) => {
      const tags = row.getValue("tags") as string[] | null

      if (!tags || tags.length === 0) {
        return <span className="text-xs text-muted-foreground italic">No tags</span>
      }

      const visible = tags.slice(0, 2)
      const overflow = tags.length - 2

      return (
        <div className="flex flex-wrap gap-1.5">
          {visible.map((tag) => {
            const tagStyle = getTagStyles(tag)
            const badgeStyle = getCategoryBadgeStyle(tagStyle.color)
            return (
              <Link key={tag} href={`/categories/${tag}`}>
                <Badge
                  variant="outline"
                  className="transition-all hover:scale-105 cursor-pointer"
                  style={badgeStyle}
                >
                  {tagStyle.displayName}
                </Badge>
              </Link>
            )
          })}
          {overflow > 0 && (
            <Badge variant="outline" className="text-muted-foreground">
              +{overflow}
            </Badge>
          )}
        </div>
      )
    },
  },
  {
    accessorKey: "created_at",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Date
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => {
      const date = row.getValue("created_at") as string
      return (
        <div className="font-mono text-sm">
          {new Date(date).toLocaleDateString()}
        </div>
      )
    },
  },
  {
    accessorKey: "source",
    header: "Source",
    cell: ({ row }) => {
      const source = row.getValue("source") as string | null

      if (!source) {
        return <span className="text-xs text-muted-foreground italic">N/A</span>
      }

      return <Badge variant="secondary">{source}</Badge>
    },
  },
]
