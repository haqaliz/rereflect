// Re-export usage and suggestions from the consolidated conversations API
// so existing CommandBar imports continue to work
export { conversationsAPI as copilotAPI } from './conversations';
export type { CopilotUsageResponse as CopilotUsage, SuggestionsResponse } from './conversations';
