"use client"

import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  Smile,
  Meh,
  Frown,
  MessageSquare,
  AlertTriangle,
  Check,
  Edit,
  Trash2,
  ArrowUpDown,
  Globe,
  Hash,
  Upload,
  Webhook,
  PenLine,
  Lightbulb
} from "lucide-react"
import Link from "next/link"
import { FeedbackItem } from "@/lib/api/feedback"
import { getTagStyles, getCategoryBadgeStyle } from "@/lib/category-utils"

const getSentimentIcon = (sentiment: string) => {
  switch (sentiment) {
    case 'positive':
      return <Smile className="w-4 h-4 text-[var(--chart-2)]" />
    case 'negative':
      return <Frown className="w-4 h-4 text-destructive" />
    case 'neutral':
      return <Meh className="w-4 h-4 text-[var(--chart-3)]" />
    default:
      return null
  }
}

const getSentimentBadgeStyle = (sentiment: string) => {
  switch (sentiment) {
    case 'positive':
      return getCategoryBadgeStyle('var(--chart-2)')
    case 'negative':
      return getCategoryBadgeStyle('var(--destructive)')
    case 'neutral':
      return getCategoryBadgeStyle('var(--chart-3)')
    default:
      return getCategoryBadgeStyle('var(--muted-foreground)')
  }
}

const getSourceIcon = (source: string | null) => {
  switch (source) {
    case 'slack':
      return <Hash className="w-3.5 h-3.5" />
    case 'webhook':
      return <Webhook className="w-3.5 h-3.5" />
    case 'csv_import':
      return <Upload className="w-3.5 h-3.5" />
    case 'manual':
      return <PenLine className="w-3.5 h-3.5" />
    default:
      return <Globe className="w-3.5 h-3.5" />
  }
}

const getSourceLabel = (source: string | null) => {
  switch (source) {
    case 'slack':
      return 'Slack'
    case 'webhook':
      return 'Webhook'
    case 'csv_import':
      return 'CSV Import'
    case 'manual':
      return 'Manual'
    default:
      return source || 'Unknown'
  }
}

export const createColumns = (
  onEdit: (item: FeedbackItem) => void,
  onDelete: (item: FeedbackItem) => void
): ColumnDef<FeedbackItem>[] => [
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
      const suggestedAction = row.original.suggested_action
      return (
        <div className="max-w-md">
          <div className="line-clamp-2 leading-relaxed">{text}</div>
          {suggestedAction && (
            <div className="flex items-start gap-1.5 mt-1.5 text-xs text-muted-foreground">
              <Lightbulb className="w-3.5 h-3.5 flex-shrink-0 mt-0.5" style={{ color: 'var(--chart-2)' }} />
              <span className="line-clamp-1">{suggestedAction}</span>
            </div>
          )}
        </div>
      )
    },
  },
  {
    id: "source_info",
    header: "Source",
    cell: ({ row }) => {
      const item = row.original
      const source = item.source
      const sourceName = item.source_name
      const metadata = item.source_metadata

      // Build display: source type + name (if available) + channel (if Slack)
      const channelName = metadata?.channel_name

      return (
        <div className="flex flex-col gap-0.5">
          <div className="flex items-center gap-1.5 text-sm">
            {getSourceIcon(source)}
            <span className="font-medium">{getSourceLabel(source)}</span>
          </div>
          {(sourceName || channelName) && (
            <span className="text-xs text-muted-foreground truncate max-w-[120px]">
              {sourceName || (channelName ? `#${channelName}` : null)}
            </span>
          )}
        </div>
      )
    },
  },
  {
    accessorKey: "sentiment_label",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Sentiment
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => {
      const sentiment = row.getValue("sentiment_label") as string | null

      if (!sentiment) {
        return (
          <span className="text-muted-foreground text-sm flex items-center space-x-1.5">
            <MessageSquare className="w-4 h-4" />
            <span>Not analyzed</span>
          </span>
        )
      }

      return (
        <div className="flex items-center space-x-2">
          {getSentimentIcon(sentiment)}
          <Badge
            variant="outline"
            style={getSentimentBadgeStyle(sentiment)}
          >
            {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
          </Badge>
        </div>
      )
    },
    filterFn: (row, id, value) => {
      return value.includes(row.getValue(id))
    },
  },
  {
    accessorKey: "tags",
    header: "Categories",
    cell: ({ row }) => {
      const tags = row.getValue("tags") as string[] | null

      if (!tags || tags.length === 0) {
        return <span className="text-muted-foreground text-sm">-</span>
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
                  className="hover:scale-105 transition-transform cursor-pointer"
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
    accessorKey: "churn_risk_score",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Churn Risk
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => {
      const score = row.getValue("churn_risk_score") as number | null

      if (score === null || score === undefined) {
        return <span className="text-muted-foreground text-sm">-</span>
      }

      const getRiskLevel = (s: number) => {
        if (s > 70) return { label: 'High', color: 'var(--destructive)' }
        if (s >= 40) return { label: 'Medium', color: 'var(--chart-2)' }
        return { label: 'Low', color: 'var(--chart-5)' }
      }

      const risk = getRiskLevel(score)

      return (
        <div className="flex items-center gap-2">
          <div
            className="w-2 h-2 rounded-full flex-shrink-0"
            style={{ backgroundColor: risk.color }}
          />
          <Badge
            variant="outline"
            style={getCategoryBadgeStyle(risk.color)}
          >
            {score}
          </Badge>
        </div>
      )
    },
  },
  {
    accessorKey: "is_urgent",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Status
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => {
      const isUrgent = row.getValue("is_urgent") as boolean

      return isUrgent ? (
        <Badge variant="destructive">
          <AlertTriangle className="w-3 h-3 mr-1" />
          Urgent
        </Badge>
      ) : (
        <Badge variant="secondary">
          <Check className="w-3 h-3 mr-1" />
          Normal
        </Badge>
      )
    },
    filterFn: (row, id, value) => {
      return value.includes(row.getValue(id))
    },
  },
  {
    id: "actions",
    header: "Actions",
    cell: ({ row }) => {
      const item = row.original

      return (
        <div className="flex items-center space-x-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onEdit(item)}
            title="Edit feedback"
            className="h-8 w-8 p-0"
          >
            <Edit className="w-4 h-4" />
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onDelete(item)}
            title="Delete feedback"
            className="h-8 w-8 p-0 text-destructive hover:text-destructive"
          >
            <Trash2 className="w-4 h-4" />
          </Button>
        </div>
      )
    },
  },
]
