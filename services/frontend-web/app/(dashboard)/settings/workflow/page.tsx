'use client';

import { useEffect, useState } from 'react';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Badge } from '@/components/ui/badge';
import { workflowAPI, AssignmentRule } from '@/lib/api/workflow';
import { teamAPI, TeamMember } from '@/lib/api/team';
import { toast } from 'sonner';
import {
  Edit,
  Trash2,
  Plus,
  Check,
  X,
} from 'lucide-react';

// Field display mapping
const FIELD_DISPLAY_MAP: Record<string, string> = {
  pain_point_category: 'Pain Point Category',
  feature_request_category: 'Feature Request Category',
  urgent_category: 'Urgent Category',
  source: 'Source',
  sentiment_label: 'Sentiment',
};

interface RuleFormData {
  match_field: string;
  match_value: string;
  assign_to_user_id: number;
  priority: number;
}

export default function WorkflowPage() {
  const [autoAssignEnabled, setAutoAssignEnabled] = useState(false);
  const [rules, setRules] = useState<AssignmentRule[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [savingAutoAssign, setSavingAutoAssign] = useState(false);

  // Form state
  const [isAddingRule, setIsAddingRule] = useState(false);
  const [editingRuleId, setEditingRuleId] = useState<number | null>(null);
  const [formData, setFormData] = useState<RuleFormData>({
    match_field: 'pain_point_category',
    match_value: '',
    assign_to_user_id: 0,
    priority: 1,
  });

  useEffect(() => {
    fetchData();
  }, []);

  const fetchData = async () => {
    setLoading(true);
    try {
      const [settingsData, rulesData, teamData] = await Promise.all([
        workflowAPI.getAutoAssignmentSettings(),
        workflowAPI.getAssignmentRules(),
        teamAPI.getTeam(),
      ]);

      setAutoAssignEnabled(settingsData.auto_assignment_enabled);
      setRules(rulesData);
      setTeamMembers(teamData.members);

      // Set default user if available
      if (teamData.members.length > 0 && formData.assign_to_user_id === 0) {
        setFormData((prev) => ({ ...prev, assign_to_user_id: teamData.members[0].id }));
      }
    } catch (err) {
      console.error('Failed to load workflow settings:', err);
      toast.error('Failed to load workflow settings');
    } finally {
      setLoading(false);
    }
  };

  const handleToggleAutoAssign = async (checked: boolean) => {
    setSavingAutoAssign(true);
    try {
      await workflowAPI.updateAutoAssignmentSettings({ auto_assignment_enabled: checked });
      setAutoAssignEnabled(checked);
      toast.success(`Auto-assignment ${checked ? 'enabled' : 'disabled'}`);
    } catch (err) {
      console.error('Failed to update auto-assignment:', err);
      toast.error('Failed to update auto-assignment');
    } finally {
      setSavingAutoAssign(false);
    }
  };

  const handleToggleRuleActive = async (ruleId: number, isActive: boolean) => {
    try {
      const updatedRule = await workflowAPI.updateRule(ruleId, { is_active: isActive });
      setRules((prev) => prev.map((r) => (r.id === ruleId ? updatedRule : r)));
      toast.success(`Rule ${isActive ? 'activated' : 'deactivated'}`);
    } catch (err) {
      console.error('Failed to toggle rule:', err);
      toast.error('Failed to toggle rule');
    }
  };

  const handleSaveRule = async () => {
    if (!formData.match_value.trim()) {
      toast.error('Match value is required');
      return;
    }

    if (formData.assign_to_user_id === 0) {
      toast.error('Please select a team member to assign to');
      return;
    }

    try {
      if (editingRuleId !== null) {
        // Update existing rule
        const updatedRule = await workflowAPI.updateRule(editingRuleId, {
          match_field: formData.match_field,
          match_value: formData.match_value,
          assign_to_user_id: formData.assign_to_user_id,
          priority: formData.priority,
        });
        setRules((prev) => prev.map((r) => (r.id === editingRuleId ? updatedRule : r)));
        toast.success('Rule updated successfully');
      } else {
        // Create new rule
        const newRule = await workflowAPI.createRule({
          match_field: formData.match_field,
          match_value: formData.match_value,
          assign_to_user_id: formData.assign_to_user_id,
          priority: formData.priority,
          is_active: true,
        });
        setRules((prev) => [...prev, newRule]);
        toast.success('Rule created successfully');
      }

      // Reset form
      setIsAddingRule(false);
      setEditingRuleId(null);
      setFormData({
        match_field: 'pain_point_category',
        match_value: '',
        assign_to_user_id: teamMembers[0]?.id || 0,
        priority: 1,
      });
    } catch (err) {
      console.error('Failed to save rule:', err);
      toast.error('Failed to save rule');
    }
  };

  const handleCancelEdit = () => {
    setIsAddingRule(false);
    setEditingRuleId(null);
    setFormData({
      match_field: 'pain_point_category',
      match_value: '',
      assign_to_user_id: teamMembers[0]?.id || 0,
      priority: 1,
    });
  };

  const handleEditRule = (rule: AssignmentRule) => {
    setFormData({
      match_field: rule.match_field,
      match_value: rule.match_value,
      assign_to_user_id: rule.assign_to_user_id,
      priority: rule.priority,
    });
    setEditingRuleId(rule.id);
    setIsAddingRule(true);
  };

  const handleDeleteRule = async (ruleId: number) => {
    if (!confirm('Are you sure you want to delete this rule?')) {
      return;
    }

    try {
      await workflowAPI.deleteRule(ruleId);
      setRules((prev) => prev.filter((r) => r.id !== ruleId));
      toast.success('Rule deleted successfully');
    } catch (err) {
      console.error('Failed to delete rule:', err);
      toast.error('Failed to delete rule');
    }
  };

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="flex flex-col items-center space-y-4">
          <div className="relative w-16 h-16">
            <div className="absolute inset-0 border-4 border-primary/20 rounded-full"></div>
            <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
          </div>
          <p className="text-muted-foreground font-medium">Loading workflow settings...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Section 1: Auto-Assignment Toggle */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader className="border-b border-border">
            <CardTitle>Auto-Assignment</CardTitle>
            <CardDescription>
              Automatically assign new feedback to team members based on rules or round-robin
            </CardDescription>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="flex items-center justify-between">
              <div>
                <p className="font-semibold text-foreground">Enable Auto-Assignment</p>
                <p className="text-sm text-muted-foreground">
                  New feedback will be automatically assigned when created
                </p>
              </div>
              <Switch
                checked={autoAssignEnabled}
                onCheckedChange={handleToggleAutoAssign}
                disabled={savingAutoAssign}
              />
            </div>
          </CardContent>
        </Card>

        {/* Section 2: Assignment Rules */}
        <Card className="animate-slide-up stagger-2">
          <CardHeader className="border-b border-border">
            <div className="flex items-center justify-between">
              <div>
                <CardTitle>Assignment Rules</CardTitle>
                <CardDescription>
                  Route feedback to specific team members based on category matches. Rules are checked in priority order (highest first). If no rule matches, round-robin is used.
                </CardDescription>
              </div>
              {!isAddingRule && (
                <Button
                  onClick={() => setIsAddingRule(true)}
                  size="sm"
                  className="flex items-center space-x-2"
                >
                  <Plus className="w-4 h-4" />
                  <span>Add Rule</span>
                </Button>
              )}
            </div>
          </CardHeader>
          <CardContent className="pt-6">
            {/* Inline Form for Add/Edit */}
            {isAddingRule && (
              <div className="mb-6 p-4 border border-border rounded-lg bg-muted/30 space-y-4">
                <h4 className="font-semibold text-foreground">
                  {editingRuleId !== null ? 'Edit Rule' : 'New Rule'}
                </h4>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="match_field">Match Field</Label>
                    <Select
                      value={formData.match_field}
                      onValueChange={(value) => setFormData({ ...formData, match_field: value })}
                    >
                      <SelectTrigger id="match_field">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {Object.entries(FIELD_DISPLAY_MAP).map(([value, label]) => (
                          <SelectItem key={value} value={value}>
                            {label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="match_value">Match Value</Label>
                    <Input
                      id="match_value"
                      type="text"
                      placeholder="e.g., Billing Issues"
                      value={formData.match_value}
                      onChange={(e) => setFormData({ ...formData, match_value: e.target.value })}
                    />
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="assign_to">Assign To</Label>
                    <Select
                      value={formData.assign_to_user_id.toString()}
                      onValueChange={(value) =>
                        setFormData({ ...formData, assign_to_user_id: parseInt(value) })
                      }
                    >
                      <SelectTrigger id="assign_to">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {teamMembers.map((member) => (
                          <SelectItem key={member.id} value={member.id.toString()}>
                            {member.email}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>

                  <div className="space-y-2">
                    <Label htmlFor="priority">Priority</Label>
                    <Input
                      id="priority"
                      type="number"
                      min="1"
                      value={formData.priority}
                      onChange={(e) =>
                        setFormData({ ...formData, priority: parseInt(e.target.value) || 1 })
                      }
                    />
                  </div>
                </div>

                <div className="flex gap-2 pt-2">
                  <Button onClick={handleSaveRule} size="sm" className="flex items-center space-x-2">
                    <Check className="w-4 h-4" />
                    <span>{editingRuleId !== null ? 'Update' : 'Save'}</span>
                  </Button>
                  <Button
                    onClick={handleCancelEdit}
                    variant="outline"
                    size="sm"
                    className="flex items-center space-x-2"
                  >
                    <X className="w-4 h-4" />
                    <span>Cancel</span>
                  </Button>
                </div>
              </div>
            )}

            {/* Rules Table */}
            {rules.length === 0 ? (
              <div className="text-center py-8 text-muted-foreground">
                No assignment rules configured. Click "Add Rule" to create one.
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead>
                    <tr className="border-b border-border">
                      <th className="text-left py-3 px-4 text-sm font-semibold text-muted-foreground">
                        Match Field
                      </th>
                      <th className="text-left py-3 px-4 text-sm font-semibold text-muted-foreground">
                        Match Value
                      </th>
                      <th className="text-left py-3 px-4 text-sm font-semibold text-muted-foreground">
                        Assign To
                      </th>
                      <th className="text-left py-3 px-4 text-sm font-semibold text-muted-foreground">
                        Priority
                      </th>
                      <th className="text-left py-3 px-4 text-sm font-semibold text-muted-foreground">
                        Active
                      </th>
                      <th className="text-left py-3 px-4 text-sm font-semibold text-muted-foreground">
                        Actions
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {rules
                      .sort((a, b) => b.priority - a.priority)
                      .map((rule) => (
                        <tr key={rule.id} className="border-b border-border hover:bg-muted/30">
                          <td className="py-3 px-4 text-sm">
                            <Badge variant="outline">
                              {FIELD_DISPLAY_MAP[rule.match_field] || rule.match_field}
                            </Badge>
                          </td>
                          <td className="py-3 px-4 text-sm font-medium">{rule.match_value}</td>
                          <td className="py-3 px-4 text-sm text-muted-foreground">
                            {rule.assign_to_email}
                          </td>
                          <td className="py-3 px-4 text-sm">
                            <Badge variant="secondary">{rule.priority}</Badge>
                          </td>
                          <td className="py-3 px-4">
                            <Switch
                              checked={rule.is_active}
                              onCheckedChange={(checked) => handleToggleRuleActive(rule.id, checked)}
                            />
                          </td>
                          <td className="py-3 px-4">
                            <div className="flex items-center gap-2">
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleEditRule(rule)}
                                className="h-8 w-8 p-0"
                              >
                                <Edit className="w-4 h-4" />
                              </Button>
                              <Button
                                variant="ghost"
                                size="sm"
                                onClick={() => handleDeleteRule(rule.id)}
                                className="h-8 w-8 p-0 text-destructive hover:text-destructive"
                              >
                                <Trash2 className="w-4 h-4" />
                              </Button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

      </main>
    </div>
  );
}
