"use client"

import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  ArrowUpDown,
  Smile,
  Frown,
  Meh,
  MessageSquare
} from "lucide-react"
import Link from "next/link"
import { FeedbackItem } from "@/lib/api/feedback"
import {
  getTagStyles,
  getCategoryBadgeStyle
} from "@/lib/category-utils"

const getSentimentIcon = (sentiment: string | null) => {
  switch (sentiment) {
    case 'positive':
      return <Smile className="w-5 h-5 text-[var(--chart-2)]" />
    case 'negative':
      return <Frown className="w-5 h-5 text-destructive" />
    case 'neutral':
      return <Meh className="w-5 h-5 text-[var(--chart-3)]" />
    default:
      return <MessageSquare className="w-5 h-5 text-muted-foreground" />
  }
}

const getSentimentBadgeStyle = (sentiment: string | null) => {
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
          <div className="p-2 rounded-lg bg-secondary">
            {getSentimentIcon(sentiment)}
          </div>
          <Badge
            variant="outline"
            style={getSentimentBadgeStyle(sentiment)}
          >
            {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
          </Badge>
        </div>
      )
    },
  },
  {
    accessorKey: "tags",
    header: "Categories",
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
