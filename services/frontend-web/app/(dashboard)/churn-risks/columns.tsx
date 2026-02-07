"use client"

import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  ArrowUpDown,
  Smile,
  Meh,
  Frown,
  MessageSquare,
  Lightbulb,
} from "lucide-react"
import { FeedbackItem } from "@/lib/api/feedback"
import { getCategoryBadgeStyle } from "@/lib/category-utils"

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

const getRiskLevel = (score: number) => {
  if (score > 70) return { label: 'Critical', color: 'var(--destructive)' }
  if (score > 50) return { label: 'High', color: 'var(--chart-1)' }
  if (score >= 40) return { label: 'Medium', color: 'var(--chart-2)' }
  return { label: 'Low', color: 'var(--chart-5)' }
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
    accessorKey: "churn_risk_score",
    header: ({ column }) => {
      return (
        <Button
          variant="ghost"
          onClick={() => column.toggleSorting(column.getIsSorted() === "asc")}
          className="h-8 px-2 lg:px-3"
        >
          Risk Score
          <ArrowUpDown className="ml-2 h-4 w-4" />
        </Button>
      )
    },
    cell: ({ row }) => {
      const score = row.getValue("churn_risk_score") as number
      const risk = getRiskLevel(score)

      return (
        <div className="flex items-center gap-2">
          <div
            className="relative w-10 h-10 rounded-xl flex items-center justify-center font-bold font-mono text-sm"
            style={{
              backgroundColor: `color-mix(in oklch, ${risk.color} 15%, transparent)`,
              color: risk.color,
              border: `2px solid color-mix(in oklch, ${risk.color} 30%, transparent)`,
            }}
          >
            {score}
          </div>
          <Badge
            variant="outline"
            style={getCategoryBadgeStyle(risk.color)}
          >
            {risk.label}
          </Badge>
        </div>
      )
    },
  },
  {
    accessorKey: "text",
    header: "Feedback",
    cell: ({ row }) => {
      const text = row.getValue("text") as string
      return <div className="max-w-md line-clamp-2 leading-relaxed">{text}</div>
    },
  },
  {
    accessorKey: "sentiment_label",
    header: "Sentiment",
    cell: ({ row }) => {
      const sentiment = row.getValue("sentiment_label") as string | null

      if (!sentiment) {
        return (
          <span className="text-muted-foreground text-sm flex items-center gap-1.5">
            <MessageSquare className="w-4 h-4" />
            <span>N/A</span>
          </span>
        )
      }

      const sentimentColor = sentiment === 'positive' ? 'var(--chart-2)' :
                             sentiment === 'negative' ? 'var(--destructive)' :
                             'var(--chart-3)'

      return (
        <div className="flex items-center gap-2">
          {getSentimentIcon(sentiment)}
          <Badge
            variant="outline"
            style={getCategoryBadgeStyle(sentimentColor)}
          >
            {sentiment.charAt(0).toUpperCase() + sentiment.slice(1)}
          </Badge>
        </div>
      )
    },
  },
  {
    accessorKey: "suggested_action",
    header: "Suggested Action",
    cell: ({ row }) => {
      const action = row.getValue("suggested_action") as string | null

      if (!action) {
        return <span className="text-muted-foreground text-sm">-</span>
      }

      return (
        <div className="flex items-start gap-2 max-w-xs">
          <Lightbulb className="w-4 h-4 text-[var(--chart-2)] flex-shrink-0 mt-0.5" />
          <span className="text-sm line-clamp-2 leading-relaxed">{action}</span>
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
        <div className="font-mono">
          <div className="flex flex-col space-y-1">
            <span className="text-sm">{new Date(date).toLocaleDateString()}</span>
            <span className="text-xs text-muted-foreground">{new Date(date).toLocaleTimeString()}</span>
          </div>
        </div>
      )
    },
  },
]
