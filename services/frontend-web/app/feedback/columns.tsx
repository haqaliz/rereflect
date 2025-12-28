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
  ArrowUpDown
} from "lucide-react"
import Link from "next/link"
import { FeedbackItem } from "@/lib/api/feedback"

const getSentimentIcon = (sentiment: string) => {
  switch (sentiment) {
    case 'positive':
      return <Smile className="w-4 h-4 text-success-text" />
    case 'negative':
      return <Frown className="w-4 h-4 text-error-text" />
    case 'neutral':
      return <Meh className="w-4 h-4 text-warning-text" />
    default:
      return null
  }
}

const getTagVariant = (tag: string): "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info" => {
  const tagMap: Record<string, "default" | "secondary" | "destructive" | "outline" | "success" | "warning" | "info"> = {
    'pain_point': 'destructive',
    'feature_request': 'info',
    'ui/ux': 'warning',
    'performance': 'warning',
    'mobile': 'secondary',
    'search': 'info',
    'documentation': 'secondary',
    'accessibility': 'success',
    'integration': 'warning',
    'notification': 'warning',
    'support': 'info',
  }
  return tagMap[tag.toLowerCase()] || 'outline'
}

const getTagDisplayName = (tag: string): string => {
  const nameMap: Record<string, string> = {
    'pain_point': 'Pain Point',
    'feature_request': 'Feature Request',
    'ui/ux': 'UI/UX',
    'performance': 'Performance',
    'mobile': 'Mobile',
    'search': 'Search',
    'documentation': 'Documentation',
    'accessibility': 'Accessibility',
    'integration': 'Integration',
    'notification': 'Notification',
    'support': 'Support',
  }
  return nameMap[tag.toLowerCase()] || tag
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
      return <div className="max-w-md line-clamp-2 leading-relaxed">{text}</div>
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
            variant={
              sentiment === 'positive'
                ? 'success'
                : sentiment === 'negative'
                ? 'destructive'
                : 'warning'
            }
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
            return (
              <Link key={tag} href={`/categories/${tag}`}>
                <Badge
                  variant={getTagVariant(tag)}
                  className="hover:scale-105 transition-transform cursor-pointer"
                >
                  {getTagDisplayName(tag)}
                </Badge>
              </Link>
            )
          })}
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
