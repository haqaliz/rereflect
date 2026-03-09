"use client"

import { ColumnDef } from "@tanstack/react-table"
import { Checkbox } from "@/components/ui/checkbox"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"
import {
  CircleAlert,
  ArrowUpDown,
  ServerOff,
  ShieldOff,
  CreditCard,
  HardDrive,
  Lock,
  Bug,
  Receipt,
  UserMinus,
  Scale,
  Megaphone
} from "lucide-react"
import Link from "next/link"
import { FeedbackItem } from "@/lib/api/feedback"
import {
  getUrgentLabel,
  getUrgentColor,
  getCategoryBadgeStyle,
  getResponseTimeLabel,
  getTagStyles
} from "@/lib/category-utils"

const getCategoryIcon = (category: string) => {
  const iconMap: Record<string, React.ReactNode> = {
    'service_outage': <ServerOff className="w-3.5 h-3.5" />,
    'data_breach': <ShieldOff className="w-3.5 h-3.5" />,
    'payment_failure': <CreditCard className="w-3.5 h-3.5" />,
    'data_corruption': <HardDrive className="w-3.5 h-3.5" />,
    'account_locked': <Lock className="w-3.5 h-3.5" />,
    'critical_bug': <Bug className="w-3.5 h-3.5" />,
    'billing_dispute': <Receipt className="w-3.5 h-3.5" />,
    'churn_risk': <UserMinus className="w-3.5 h-3.5" />,
    'compliance': <Scale className="w-3.5 h-3.5" />,
    'reputation_risk': <Megaphone className="w-3.5 h-3.5" />,
  }
  return iconMap[category] || <CircleAlert className="w-3.5 h-3.5" />
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
                <CircleAlert className="w-4 h-4 text-primary" />
              </div>
            </div>
            <div className="flex-1">
              <p className="line-clamp-2 leading-relaxed mb-2">{text}</p>
              <Badge variant="destructive">URGENT</Badge>
            </div>
          </div>
        </div>
      )
    },
  },
  {
    accessorKey: "urgent_category",
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
      const category = row.getValue("urgent_category") as string | null
      const responseTime = row.original.urgent_response_time

      if (!category) {
        return <span className="text-xs text-muted-foreground italic">Uncategorized</span>
      }

      const categoryColor = getUrgentColor(category)
      const categoryStyle = getCategoryBadgeStyle(categoryColor)

      return (
        <div className="flex flex-col gap-1.5">
          <Badge
            variant="outline"
            className="flex items-center gap-1.5 w-fit transition-all hover:scale-105"
            style={categoryStyle}
          >
            {getCategoryIcon(category)}
            {getUrgentLabel(category)}
          </Badge>
          <span className="text-xs" style={{ color: categoryColor }}>
            Respond: {getResponseTimeLabel(responseTime || 'immediate')}
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
          Date & Time
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
