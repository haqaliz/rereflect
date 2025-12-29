"use client"

import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Lightbulb,
  ArrowUpDown,
  Boxes,
  Workflow,
  Plug,
  BarChart3,
  Settings2,
  Users,
  Smartphone,
  Bell,
  Palette
} from "lucide-react"
import Link from "next/link"
import { FeedbackItem } from "@/lib/api/feedback"
import {
  getFeatureRequestLabel,
  getFeatureRequestColor,
  getCategoryBadgeStyle,
  getTagStyles
} from "@/lib/category-utils"

const getCategoryIcon = (category: string) => {
  const iconMap: Record<string, React.ReactNode> = {
    'core_functionality': <Boxes className="w-3.5 h-3.5" />,
    'automation': <Workflow className="w-3.5 h-3.5" />,
    'integration': <Plug className="w-3.5 h-3.5" />,
    'reporting': <BarChart3 className="w-3.5 h-3.5" />,
    'customization': <Settings2 className="w-3.5 h-3.5" />,
    'collaboration': <Users className="w-3.5 h-3.5" />,
    'export_import': <ArrowUpDown className="w-3.5 h-3.5" />,
    'mobile': <Smartphone className="w-3.5 h-3.5" />,
    'notifications': <Bell className="w-3.5 h-3.5" />,
    'ui_enhancement': <Palette className="w-3.5 h-3.5" />,
  }
  return iconMap[category] || <Lightbulb className="w-3.5 h-3.5" />
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
      return (
        <div className="max-w-md">
          <div className="flex items-start space-x-3">
            <div className="flex-shrink-0 mt-1">
              <div className="p-2 rounded-lg bg-secondary">
                <Lightbulb className="w-4 h-4 text-primary" />
              </div>
            </div>
            <p className="line-clamp-2 leading-relaxed">{text}</p>
          </div>
        </div>
      )
    },
  },
  {
    accessorKey: "feature_request_category",
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
      const category = row.getValue("feature_request_category") as string | null
      const priority = row.original.feature_request_priority

      if (!category) {
        return <span className="text-xs text-muted-foreground italic">Uncategorized</span>
      }

      const categoryColor = getFeatureRequestColor(category)
      const categoryStyle = getCategoryBadgeStyle(categoryColor)

      return (
        <div className="flex flex-col gap-1.5">
          <Badge
            variant="outline"
            className="flex items-center gap-1.5 w-fit transition-all hover:scale-105"
            style={categoryStyle}
          >
            {getCategoryIcon(category)}
            {getFeatureRequestLabel(category)}
          </Badge>
          <span className="text-xs capitalize" style={{ color: categoryColor }}>
            {priority || 'medium'} Priority
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

      return (
        <div className="flex flex-wrap gap-1.5">
          {tags.map((tag) => {
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
