'use client';

import { DragDropContext, Droppable, Draggable, DropResult } from '@hello-pangea/dnd';
import { WorkflowFeedbackItem } from '@/lib/api/workflow';
import { WORKFLOW_STATUSES, getStatusColor, getStatusLabel } from '@/lib/workflow-utils';
import { KanbanCard } from './kanban-card';

interface KanbanViewProps {
  items: WorkflowFeedbackItem[];
  onStatusChange: (id: number, newStatus: string) => void;
  statusCounts: Record<string, number>;
}

export function KanbanView({
  items,
  onStatusChange,
  statusCounts,
}: KanbanViewProps) {
  const onDragEnd = (result: DropResult) => {
    const { destination, source, draggableId } = result;

    if (!destination) return;
    if (destination.droppableId === source.droppableId) return;

    const itemId = parseInt(draggableId.replace('item-', ''), 10);
    const newStatus = destination.droppableId;

    onStatusChange(itemId, newStatus);
  };

  const getItemsForStatus = (status: string) => {
    return items.filter((item) => item.workflow_status === status);
  };

  return (
    <DragDropContext onDragEnd={onDragEnd}>
      <div className="overflow-x-auto">
        <div className="flex gap-4 pb-4" style={{ minWidth: 'max-content' }}>
          {WORKFLOW_STATUSES.map((status) => {
            const statusItems = getItemsForStatus(status);
            const count = statusCounts[status] || 0;
            const color = getStatusColor(status);
            const label = getStatusLabel(status);

            return (
              <div key={status} className="flex flex-col w-[360px] flex-shrink-0">
                <div className="mb-3 flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: color }}
                  />
                  <h3 className="font-semibold text-sm">
                    {label} ({count})
                  </h3>
                </div>

                <Droppable droppableId={status}>
                  {(provided, snapshot) => (
                    <div
                      className={`
                        flex-1 rounded-lg border-2 border-dashed
                        ${
                          snapshot.isDraggingOver
                            ? 'border-primary bg-primary/5'
                            : 'border-border bg-muted/20'
                        }
                      `}
                    >
                      <div
                        ref={provided.innerRef}
                        {...provided.droppableProps}
                        className="p-2 space-y-3 overflow-y-auto scrollbar-auto-hide h-[calc(100vh-440px)]"
                      >
                        {statusItems.map((item, index) => (
                          <Draggable
                            key={item.id}
                            draggableId={`item-${item.id}`}
                            index={index}
                          >
                            {(provided, snapshot) => (
                              <div
                                ref={provided.innerRef}
                                {...provided.draggableProps}
                                {...provided.dragHandleProps}
                                className={snapshot.isDragging ? 'opacity-50' : ''}
                              >
                                <KanbanCard item={item} />
                              </div>
                            )}
                          </Draggable>
                        ))}
                        {provided.placeholder}
                      </div>
                    </div>
                  )}
                </Droppable>
              </div>
            );
          })}
        </div>
      </div>
    </DragDropContext>
  );
}
