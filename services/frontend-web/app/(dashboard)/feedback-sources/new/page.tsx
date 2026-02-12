'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import Link from 'next/link';
import { Card, CardHeader, CardContent, CardTitle, CardDescription } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Checkbox } from '@/components/ui/checkbox';
import { Badge } from '@/components/ui/badge';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  feedbackSourcesAPI,
  SourceTypeInfo,
  CreateFeedbackSourceRequest,
  TRIGGER_OPTIONS,
  DEFAULT_TRIGGERS,
  DEFAULT_FIELD_MAPPING,
  TriggerConfig,
  FieldMappingConfig,
} from '@/lib/api/feedback-sources';
import { integrationsAPI, Integration } from '@/lib/api/integrations';
import {
  Slack,
  Webhook,
  MessageCircle,
  MessageSquare,
  Mail,
  ArrowLeft,
  Loader2,
  AlertCircle,
  Info,
  Check,
  Plus,
  ChevronRight,
  Inbox,
} from 'lucide-react';

// Source type icon mapping
const SOURCE_ICONS: Record<string, React.ElementType> = {
  slack: Slack,
  intercom: MessageSquare,
  webhook: Webhook,
  discord: MessageCircle,
  email: Mail,
};

// Source type colors
const SOURCE_COLORS: Record<string, string> = {
  slack: 'text-[#4A154B]',
  intercom: 'text-[#1F8DED]',
  webhook: 'text-blue-600',
  discord: 'text-[#5865F2]',
  email: 'text-amber-600',
};

type Step = 'type' | 'integration' | 'triggers' | 'mapping' | 'confirm';

function NewSourceContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const initialType = searchParams.get('type');

  // Determine initial step based on type
  const getInitialStep = (): Step => {
    if (!initialType) return 'type';
    // Types that don't require integration go to triggers
    if (initialType === 'webhook' || initialType === 'discord' || initialType === 'email') return 'triggers';
    // OAuth types (slack, intercom) require integration selection
    return 'integration';
  };

  const [step, setStep] = useState<Step>(getInitialStep());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Data
  const [sourceTypes, setSourceTypes] = useState<SourceTypeInfo[]>([]);
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loadingData, setLoadingData] = useState(true);

  // Form state
  const [selectedType, setSelectedType] = useState<string>(initialType || '');
  const [form, setForm] = useState<{
    name: string;
    integration_id: number | null;
    triggers: TriggerConfig;
    field_mapping: FieldMappingConfig;
    auto_import: boolean;
  }>({
    name: '',
    integration_id: null,
    triggers: { ...DEFAULT_TRIGGERS },
    field_mapping: { ...DEFAULT_FIELD_MAPPING },
    auto_import: true,
  });

  // Trigger value inputs
  const [reactionInput, setReactionInput] = useState('');
  const [keywordInput, setKeywordInput] = useState('');
  const [labelInput, setLabelInput] = useState('');
  const [mentionUserInput, setMentionUserInput] = useState('');

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoadingData(true);
        const [typesRes, integrationsRes] = await Promise.all([
          feedbackSourcesAPI.getTypes(),
          integrationsAPI.list(),
        ]);
        setSourceTypes(typesRes);
        setIntegrations(integrationsRes.integrations);
      } catch (err) {
        console.error('Failed to load data:', err);
      } finally {
        setLoadingData(false);
      }
    };
    fetchData();
  }, []);

  const currentTypeInfo = sourceTypes.find(t => t.type === selectedType);
  const availableIntegrations = integrations.filter(i =>
    i.integration_type === 'oauth' && i.is_active && i.type === selectedType
  );

  const handleTypeSelect = (type: string) => {
    setSelectedType(type);
    const typeInfo = sourceTypes.find(t => t.type === type);
    if (typeInfo?.requires_integration) {
      setStep('integration');
    } else {
      setStep('triggers');
    }
  };

  const handleIntegrationSelect = (integrationId: number | null) => {
    setForm(prev => ({ ...prev, integration_id: integrationId }));
    setStep('triggers');
  };

  const toggleTrigger = (key: string) => {
    setForm(prev => {
      const triggers = { ...prev.triggers };
      if (key === 'all_messages') {
        triggers.all_messages = !triggers.all_messages;
      } else if (key === 'mentions.bot') {
        triggers.mentions = {
          ...triggers.mentions,
          bot: !triggers.mentions?.bot,
        };
      }
      return { ...prev, triggers };
    });
  };

  const addReaction = () => {
    if (!reactionInput.trim()) return;
    const emoji = reactionInput.trim().replace(/:/g, '');
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        reactions: [...(prev.triggers.reactions || []), emoji],
      },
    }));
    setReactionInput('');
  };

  const removeReaction = (emoji: string) => {
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        reactions: (prev.triggers.reactions || []).filter(r => r !== emoji),
      },
    }));
  };

  const addKeyword = () => {
    if (!keywordInput.trim()) return;
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        keywords: [...(prev.triggers.keywords || []), keywordInput.trim()],
      },
    }));
    setKeywordInput('');
  };

  const removeKeyword = (keyword: string) => {
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        keywords: (prev.triggers.keywords || []).filter(k => k !== keyword),
      },
    }));
  };

  const addLabel = () => {
    if (!labelInput.trim()) return;
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        labels: [...(prev.triggers.labels || []), labelInput.trim()],
      },
    }));
    setLabelInput('');
  };

  const removeLabel = (label: string) => {
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        labels: (prev.triggers.labels || []).filter(l => l !== label),
      },
    }));
  };

  const addMentionUser = () => {
    if (!mentionUserInput.trim()) return;
    const username = mentionUserInput.trim().replace(/^@/, '');
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        mentions: {
          ...prev.triggers.mentions,
          users: [...(prev.triggers.mentions?.users || []), username],
        },
      },
    }));
    setMentionUserInput('');
  };

  const removeMentionUser = (username: string) => {
    setForm(prev => ({
      ...prev,
      triggers: {
        ...prev.triggers,
        mentions: {
          ...prev.triggers.mentions,
          users: (prev.triggers.mentions?.users || []).filter(u => u !== username),
        },
      },
    }));
  };

  const handleSubmit = async () => {
    setError(null);
    setLoading(true);

    try {
      const data: CreateFeedbackSourceRequest = {
        source_type: selectedType,
        name: form.name || undefined,
        integration_id: form.integration_id || undefined,
        triggers: form.triggers,
        field_mapping: form.field_mapping,
        auto_import: form.auto_import,
      };

      await feedbackSourcesAPI.create(data);
      router.push('/feedback-sources');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create feedback source');
    } finally {
      setLoading(false);
    }
  };

  const renderStepIndicator = () => {
    const steps: { key: Step; label: string }[] = [
      { key: 'type', label: 'Source Type' },
    ];

    if (currentTypeInfo?.requires_integration) {
      steps.push({ key: 'integration', label: 'Integration' });
    }

    steps.push(
      { key: 'triggers', label: 'Triggers' },
      { key: 'mapping', label: 'Field Mapping' },
      { key: 'confirm', label: 'Confirm' }
    );

    const currentIndex = steps.findIndex(s => s.key === step);

    return (
      <div className="flex items-center justify-center gap-2 mb-6">
        {steps.map((s, i) => (
          <div key={s.key} className="flex items-center">
            <div className="flex items-center gap-2">
              <div
                className={`flex items-center justify-center w-6 h-6 rounded-full ${
                  i < currentIndex
                    ? 'bg-primary text-primary-foreground'
                    : i === currentIndex
                    ? 'bg-primary text-primary-foreground ring-2 ring-primary/30'
                    : 'bg-muted'
                }`}
              >
                {i < currentIndex ? (
                  <Check className="w-3.5 h-3.5" />
                ) : (
                  <div className={`w-2 h-2 rounded-full ${i === currentIndex ? 'bg-primary-foreground' : 'bg-muted-foreground/50'}`} />
                )}
              </div>
              <span
                className={`text-sm font-medium hidden sm:inline ${
                  i <= currentIndex ? 'text-foreground' : 'text-muted-foreground'
                }`}
              >
                {s.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <ChevronRight className="w-4 h-4 mx-2 text-muted-foreground" />
            )}
          </div>
        ))}
      </div>
    );
  };

  if (loadingData) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <Link
            href="/feedbacks"
            className="inline-flex items-center text-sm text-muted-foreground hover:text-foreground mb-4"
          >
            <ArrowLeft className="w-4 h-4 mr-1" />
            Back to Feedbacks
          </Link>
          <div className="flex items-center space-x-3">
            <div className="p-3 bg-secondary rounded-xl">
              <Inbox className="w-8 h-8 text-primary" />
            </div>
            <div>
              <h1 className="text-3xl font-bold text-foreground">New Feedback Source</h1>
              <p className="text-muted-foreground">Configure where to receive feedback from</p>
            </div>
          </div>
        </div>

        {/* Step Indicator */}
        {renderStepIndicator()}

        {/* Step: Type Selection */}
        {step === 'type' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Select Source Type</CardTitle>
              <CardDescription>Choose where you want to receive feedback from</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {sourceTypes.map(type => {
                  const Icon = SOURCE_ICONS[type.type] || Webhook;
                  const iconColor = SOURCE_COLORS[type.type] || 'text-muted-foreground';

                  return (
                    <button
                      key={type.type}
                      onClick={() => type.available && handleTypeSelect(type.type)}
                      disabled={!type.available}
                      className={`p-4 rounded-lg border-2 text-left transition-all ${
                        !type.available
                          ? 'border-border bg-muted/30 opacity-60 cursor-not-allowed'
                          : selectedType === type.type
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:border-primary/50'
                      }`}
                    >
                      <div className="flex items-start gap-3">
                        <div className="p-2 bg-secondary rounded-lg">
                          <Icon className={`w-6 h-6 ${iconColor}`} />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground">{type.name}</span>
                            {!type.available && (
                              <Badge variant="outline" className="text-xs">Coming Soon</Badge>
                            )}
                            {type.requires_integration && type.available && (
                              <Badge variant="secondary" className="text-xs">Requires OAuth</Badge>
                            )}
                          </div>
                          <p className="text-sm text-muted-foreground mt-1">{type.description}</p>
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step: Integration Selection */}
        {step === 'integration' && (() => {
          const TypeIcon = SOURCE_ICONS[selectedType] || Webhook;
          const typeColor = SOURCE_COLORS[selectedType] || 'text-muted-foreground';
          const typeName = selectedType.charAt(0).toUpperCase() + selectedType.slice(1);

          return (
            <Card className="animate-slide-up">
              <CardHeader>
                <CardTitle>Select Integration</CardTitle>
                <CardDescription>
                  Choose an existing {typeName} integration or create a new one
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {availableIntegrations.length === 0 ? (
                  <div className="text-center py-8">
                    <TypeIcon className="w-12 h-12 mx-auto text-muted-foreground/50 mb-4" />
                    <h3 className="font-semibold text-foreground mb-2">No {typeName} integrations found</h3>
                    <p className="text-sm text-muted-foreground mb-4">
                      You need to connect {typeName} first to receive feedback from it
                    </p>
                    <Link href="/settings/integrations/new">
                      <Button>
                        <Plus className="w-4 h-4 mr-2" />
                        Connect {typeName}
                      </Button>
                    </Link>
                  </div>
                ) : (
                  <>
                    <div className="space-y-3">
                      {availableIntegrations.map(integration => (
                        <button
                          key={integration.id}
                          onClick={() => handleIntegrationSelect(integration.id)}
                          className={`w-full p-4 rounded-lg border-2 text-left transition-all ${
                            form.integration_id === integration.id
                              ? 'border-primary bg-primary/5'
                              : 'border-border hover:border-primary/50'
                          }`}
                        >
                          <div className="flex items-center gap-3">
                            <div className="p-2 bg-secondary rounded-lg">
                              <TypeIcon className={`w-5 h-5 ${typeColor}`} />
                            </div>
                            <div>
                              <div className="font-semibold text-foreground">
                                {integration.name || 'Unnamed Integration'}
                              </div>
                              <div className="text-sm text-muted-foreground">
                                {integration.team_name}
                                {integration.channel_name && ` • #${integration.channel_name}`}
                              </div>
                            </div>
                            {form.integration_id === integration.id && (
                              <Check className="w-5 h-5 text-primary ml-auto" />
                            )}
                          </div>
                        </button>
                      ))}
                    </div>

                    <div className="pt-4 border-t border-border">
                      <Link href="/settings/integrations/new" className="text-sm text-primary hover:underline">
                        + Add a new {typeName} integration
                      </Link>
                    </div>

                    <div className="flex justify-between pt-4">
                      <Button variant="outline" onClick={() => setStep('type')}>
                        Back
                      </Button>
                      <Button
                        onClick={() => setStep('triggers')}
                        disabled={!form.integration_id}
                      >
                        Continue
                      </Button>
                    </div>
                  </>
                )}
              </CardContent>
            </Card>
          );
        })()}

        {/* Step: Trigger Configuration */}
        {step === 'triggers' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Configure Triggers</CardTitle>
              <CardDescription>
                Choose when messages should be captured as feedback
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Source Name */}
              <div className="space-y-2">
                <Label htmlFor="name">Source Name (optional)</Label>
                <Input
                  id="name"
                  placeholder={`e.g., ${selectedType === 'slack' ? '#feedback-channel' : selectedType === 'intercom' ? 'Support Conversations' : 'Product Feedback Webhook'}`}
                  value={form.name}
                  onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                />
              </div>

              {/* Trigger Options */}
              <div className="space-y-4">
                <Label className="text-base">Triggers</Label>

                {TRIGGER_OPTIONS[selectedType]?.map(trigger => {
                  const isEnabled = trigger.key === 'all_messages'
                    ? form.triggers.all_messages
                    : trigger.key === 'mentions.bot'
                    ? form.triggers.mentions?.bot
                    : false;

                  return (
                    <div key={trigger.key} className="space-y-2">
                      <div className="flex items-center space-x-3">
                        {!trigger.hasValues && (
                          <Checkbox
                            id={`trigger-${trigger.key}`}
                            checked={isEnabled}
                            onCheckedChange={() => toggleTrigger(trigger.key)}
                          />
                        )}
                        <div className="flex-1">
                          <Label
                            htmlFor={`trigger-${trigger.key}`}
                            className={`font-medium leading-none ${trigger.hasValues ? '' : 'cursor-pointer'}`}
                          >
                            {trigger.label}
                          </Label>
                          <p className="text-xs text-muted-foreground mt-1">{trigger.description}</p>

                          {/* Reactions input */}
                          {trigger.key === 'reactions' && (
                            <div className="mt-2 space-y-2">
                              <div className="flex gap-2">
                                <Input
                                  placeholder="e.g., memo, feedback, star"
                                  value={reactionInput}
                                  onChange={e => setReactionInput(e.target.value)}
                                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addReaction())}
                                  className="flex-1"
                                />
                                <Button type="button" onClick={addReaction} size="sm">
                                  Add
                                </Button>
                              </div>
                              {form.triggers.reactions && form.triggers.reactions.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {form.triggers.reactions.map(emoji => (
                                    <Badge
                                      key={emoji}
                                      variant="secondary"
                                      className="cursor-pointer"
                                      onClick={() => removeReaction(emoji)}
                                    >
                                      :{emoji}: ×
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Keywords input */}
                          {trigger.key === 'keywords' && (
                            <div className="mt-2 space-y-2">
                              <div className="flex gap-2">
                                <Input
                                  placeholder="e.g., bug, feature request, feedback"
                                  value={keywordInput}
                                  onChange={e => setKeywordInput(e.target.value)}
                                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addKeyword())}
                                  className="flex-1"
                                />
                                <Button type="button" onClick={addKeyword} size="sm">
                                  Add
                                </Button>
                              </div>
                              {form.triggers.keywords && form.triggers.keywords.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {form.triggers.keywords.map(keyword => (
                                    <Badge
                                      key={keyword}
                                      variant="secondary"
                                      className="cursor-pointer"
                                      onClick={() => removeKeyword(keyword)}
                                    >
                                      {keyword} ×
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {/* Labels/Field Match input */}
                          {trigger.key === 'labels' && (
                            <div className="mt-2 space-y-2">
                              <div className="flex gap-2">
                                <Input
                                  placeholder="e.g., feedback, important, urgent"
                                  value={labelInput}
                                  onChange={e => setLabelInput(e.target.value)}
                                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addLabel())}
                                  className="flex-1"
                                />
                                <Button type="button" onClick={addLabel} size="sm">
                                  Add
                                </Button>
                              </div>
                              {form.triggers.labels && form.triggers.labels.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {form.triggers.labels.map(label => (
                                    <Badge
                                      key={label}
                                      variant="secondary"
                                      className="cursor-pointer"
                                      onClick={() => removeLabel(label)}
                                    >
                                      {label} ×
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}

                          {/* User Mentions input */}
                          {trigger.key === 'mentions.users' && (
                            <div className="mt-2 space-y-2">
                              <div className="flex gap-2">
                                <Input
                                  placeholder="e.g., @rereflect, @productteam"
                                  value={mentionUserInput}
                                  onChange={e => setMentionUserInput(e.target.value)}
                                  onKeyDown={e => e.key === 'Enter' && (e.preventDefault(), addMentionUser())}
                                  className="flex-1"
                                />
                                <Button type="button" onClick={addMentionUser} size="sm">
                                  Add
                                </Button>
                              </div>
                              {form.triggers.mentions?.users && form.triggers.mentions.users.length > 0 && (
                                <div className="flex flex-wrap gap-2">
                                  {form.triggers.mentions.users.map(user => (
                                    <Badge
                                      key={user}
                                      variant="secondary"
                                      className="cursor-pointer"
                                      onClick={() => removeMentionUser(user)}
                                    >
                                      @{user} ×
                                    </Badge>
                                  ))}
                                </div>
                              )}
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>

              <div className="flex justify-between pt-4 border-t border-border">
                <Button
                  variant="outline"
                  onClick={() => setStep(currentTypeInfo?.requires_integration ? 'integration' : 'type')}
                >
                  Back
                </Button>
                <Button onClick={() => setStep('mapping')}>
                  Continue
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step: Field Mapping */}
        {step === 'mapping' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Field Mapping</CardTitle>
              <CardDescription>
                Configure how source messages are converted to feedback
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Text Source */}
              <div className="space-y-2">
                <Label>Text Source</Label>
                <Select
                  value={form.field_mapping.text_source}
                  onValueChange={value =>
                    setForm(prev => ({
                      ...prev,
                      field_mapping: { ...prev.field_mapping, text_source: value as any },
                    }))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="message">Message only</SelectItem>
                    <SelectItem value="thread">Message + thread context</SelectItem>
                    <SelectItem value="full">Full thread</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  What content should be captured as feedback text
                </p>
              </div>

              {/* Include options */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <Label>Include Author Info</Label>
                    <p className="text-xs text-muted-foreground">Add author name to feedback metadata</p>
                  </div>
                  <Switch
                    checked={form.field_mapping.include_author}
                    onCheckedChange={checked =>
                      setForm(prev => ({
                        ...prev,
                        field_mapping: { ...prev.field_mapping, include_author: checked },
                      }))
                    }
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <Label>Include Source Name</Label>
                    <p className="text-xs text-muted-foreground">Add channel/source name to metadata</p>
                  </div>
                  <Switch
                    checked={form.field_mapping.include_source_name}
                    onCheckedChange={checked =>
                      setForm(prev => ({
                        ...prev,
                        field_mapping: { ...prev.field_mapping, include_source_name: checked },
                      }))
                    }
                  />
                </div>

                <div className="flex items-center justify-between">
                  <div>
                    <Label>Include Context Messages</Label>
                    <p className="text-xs text-muted-foreground">
                      Fetch previous messages from the same thread/channel to provide conversation context
                    </p>
                  </div>
                  <Switch
                    checked={form.field_mapping.include_context}
                    onCheckedChange={checked =>
                      setForm(prev => ({
                        ...prev,
                        field_mapping: { ...prev.field_mapping, include_context: checked },
                      }))
                    }
                  />
                </div>

                {form.field_mapping.include_context && (
                  <div className="ml-6 space-y-2">
                    <Label>Max Context Messages</Label>
                    <p className="text-xs text-muted-foreground mb-2">
                      Number of previous messages to include before the captured message
                    </p>
                    <Input
                      type="number"
                      min={1}
                      max={20}
                      value={form.field_mapping.max_context_messages}
                      onChange={e =>
                        setForm(prev => ({
                          ...prev,
                          field_mapping: {
                            ...prev.field_mapping,
                            max_context_messages: parseInt(e.target.value) || 5,
                          },
                        }))
                      }
                      className="w-24"
                    />
                  </div>
                )}
              </div>

              <div className="flex justify-between pt-4 border-t border-border">
                <Button variant="outline" onClick={() => setStep('triggers')}>
                  Back
                </Button>
                <Button onClick={() => setStep('confirm')}>
                  Continue
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Step: Confirm */}
        {step === 'confirm' && (
          <Card className="animate-slide-up">
            <CardHeader>
              <CardTitle>Confirm Settings</CardTitle>
              <CardDescription>Review your feedback source configuration</CardDescription>
            </CardHeader>
            <CardContent className="space-y-6">
              {/* Summary */}
              <div className="space-y-4">
                <div className="p-4 bg-muted/50 rounded-lg space-y-3">
                  <div className="flex items-center gap-2">
                    {(() => {
                      const Icon = SOURCE_ICONS[selectedType] || Webhook;
                      const iconColor = SOURCE_COLORS[selectedType] || 'text-muted-foreground';
                      return (
                        <>
                          <Icon className={`w-5 h-5 ${iconColor}`} />
                          <span className="font-semibold capitalize">{selectedType} Source</span>
                        </>
                      );
                    })()}
                  </div>

                  {form.name && (
                    <div className="text-sm">
                      <span className="text-muted-foreground">Name:</span>{' '}
                      <span className="text-foreground">{form.name}</span>
                    </div>
                  )}

                  {form.integration_id && (
                    <div className="text-sm">
                      <span className="text-muted-foreground">Integration:</span>{' '}
                      <span className="text-foreground">
                        {integrations.find(i => i.id === form.integration_id)?.name || 'Selected'}
                      </span>
                    </div>
                  )}

                  <div className="text-sm">
                    <span className="text-muted-foreground">Triggers:</span>{' '}
                    <span className="text-foreground">
                      {[
                        form.triggers.all_messages && 'All messages',
                        form.triggers.mentions?.bot && 'Bot mentions',
                        form.triggers.reactions?.length && `${form.triggers.reactions.length} reaction(s)`,
                        form.triggers.keywords?.length && `${form.triggers.keywords.length} keyword(s)`,
                      ].filter(Boolean).join(', ') || 'None configured'}
                    </span>
                  </div>

                  <div className="text-sm">
                    <span className="text-muted-foreground">Text source:</span>{' '}
                    <span className="text-foreground capitalize">{form.field_mapping.text_source}</span>
                  </div>
                </div>

                {/* Auto-import toggle */}
                <div className="flex items-center justify-between p-4 border border-border rounded-lg">
                  <div>
                    <Label className="text-base">Auto-import Feedback</Label>
                    <p className="text-sm text-muted-foreground">
                      {form.auto_import
                        ? 'Feedback will be created automatically'
                        : 'Feedback will go to pending queue for review'}
                    </p>
                  </div>
                  <Switch
                    checked={form.auto_import}
                    onCheckedChange={checked => setForm(prev => ({ ...prev, auto_import: checked }))}
                  />
                </div>

                {!form.auto_import && (
                  <div className="p-3 bg-amber-50 dark:bg-amber-950 text-amber-700 dark:text-amber-300 rounded-lg flex items-start gap-2 text-sm">
                    <Info className="w-4 h-4 mt-0.5 flex-shrink-0" />
                    <span>
                      Captured messages will appear in the pending queue. You can approve or reject
                      them before they become feedback items.
                    </span>
                  </div>
                )}
              </div>

              <div className="flex justify-between pt-4 border-t border-border">
                <Button variant="outline" onClick={() => setStep('mapping')}>
                  Back
                </Button>
                <Button onClick={handleSubmit} disabled={loading}>
                  {loading && <Loader2 className="w-4 h-4 mr-2 animate-spin" />}
                  Create Source
                </Button>
              </div>
            </CardContent>
          </Card>
        )}

        {/* Error */}
        {error && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-lg flex items-center gap-2">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            {error}
          </div>
        )}
      </main>
    </div>
  );
}

export default function NewSourcePage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen pattern-bg">
        <main className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    }>
      <NewSourceContent />
    </Suspense>
  );
}
