'use client';

import { useState, useEffect, Suspense } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { Card, CardHeader, CardContent, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  integrationsAPI,
  Integration,
  TRIGGER_OPTIONS,
} from '@/lib/api/integrations';
import {
  Plus,
  Trash2,
  Send,
  CheckCircle,
  XCircle,
  AlertCircle,
  Loader2,
  Settings2,
  Clock,
  ChevronRight,
  Link as LinkIcon,
  Webhook,
  Settings as SettingsIcon,
  MessageSquare,
  Users,
  Activity,
} from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { SlackIcon } from '@/components/icons/SlackIcon';
import { IntercomIcon } from '@/components/icons/IntercomIcon';
import { LinearIcon } from '@/components/icons/LinearIcon';
import { SalesforceIcon } from '@/components/icons/SalesforceIcon';
import { JiraIcon } from '@/components/icons/JiraIcon';
import { useAuth } from '@/contexts/AuthContext';
import Link from 'next/link';
import { linearAPI, LinearConnectionStatus } from '@/lib/api/linear';
import { hubspotAPI, HubSpotConnectionStatus } from '@/lib/api/hubspot';
import { salesforceAPI, SalesforceConnectionStatus } from '@/lib/api/salesforce';
import { jiraAPI, JiraConnectionStatus } from '@/lib/api/jira';
import { getOauthErrorMessage } from '@/lib/oauthErrors';

function IntegrationsContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user } = useAuth();
  const [integrations, setIntegrations] = useState<Integration[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingId, setTestingId] = useState<number | null>(null);
  const [testResult, setTestResult] = useState<{ id: number; success: boolean; message: string } | null>(null);
  const [oauthError, setOauthError] = useState<string | null>(null);
  const [linearStatus, setLinearStatus] = useState<LinearConnectionStatus | null>(null);
  const [hubspotStatus, setHubspotStatus] = useState<HubSpotConnectionStatus | null>(null);
  const [salesforceStatus, setSalesforceStatus] = useState<SalesforceConnectionStatus | null>(null);
  const [jiraStatus, setJiraStatus] = useState<JiraConnectionStatus | null>(null);
  const [linearTesting, setLinearTesting] = useState(false);
  const [linearTestResult, setLinearTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [salesforceTesting, setSalesforceTesting] = useState(false);
  const [salesforceTestResult, setSalesforceTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [jiraTesting, setJiraTesting] = useState(false);
  const [jiraTestResult, setJiraTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [confirmAction, setConfirmAction] = useState<(() => void) | null>(null);
  const [confirmMessage, setConfirmMessage] = useState('');

  const requestConfirm = (message: string, action: () => void) => {
    setConfirmMessage(message);
    setConfirmAction(() => action);
  };

  // Only admin/owner can manage integrations
  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  // Redirect non-admin/owner to preferences
  useEffect(() => {
    if (user && user.role !== 'owner' && user.role !== 'admin') {
      router.replace('/settings/preferences');
    }
  }, [user, router]);

  useEffect(() => {
    // Don't fetch if user is not admin/owner (will be redirected)
    if (user && user.role !== 'owner' && user.role !== 'admin') {
      return;
    }

    // Check for OAuth error in URL
    const error = searchParams.get('oauth_error');
    if (error) {
      setOauthError(getOauthErrorMessage(error));
      // Clean up URL
      router.replace('/settings/integrations', { scroll: false });
    }

    fetchData();
  }, [searchParams, router]);

  const fetchData = async () => {
    try {
      setLoading(true);
      const [integrationResponse, linearStatusResponse, hubspotStatusResponse, salesforceStatusResponse, jiraStatusResponse] = await Promise.allSettled([
        integrationsAPI.list(),
        linearAPI.getStatus(),
        hubspotAPI.getStatus(),
        salesforceAPI.getStatus(),
        jiraAPI.getStatus(),
      ]);
      if (integrationResponse.status === 'fulfilled') {
        setIntegrations(integrationResponse.value.integrations);
      }
      if (linearStatusResponse.status === 'fulfilled') {
        setLinearStatus(linearStatusResponse.value);
      }
      if (hubspotStatusResponse.status === 'fulfilled') {
        setHubspotStatus(hubspotStatusResponse.value);
      }
      if (salesforceStatusResponse.status === 'fulfilled') {
        setSalesforceStatus(salesforceStatusResponse.value);
      }
      if (jiraStatusResponse.status === 'fulfilled') {
        setJiraStatus(jiraStatusResponse.value);
      }
    } catch (err) {
      console.error('Failed to load integrations:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleTest = async (integration: Integration) => {
    setTestingId(integration.id);
    setTestResult(null);
    try {
      const result = await integrationsAPI.testSlack(integration.id);
      setTestResult({ id: integration.id, success: result.success, message: result.message });
      await fetchData();
    } catch (err: any) {
      setTestResult({
        id: integration.id,
        success: false,
        message: err.response?.data?.detail || 'Test failed',
      });
    } finally {
      setTestingId(null);
    }
  };

  const handleDelete = (integration: Integration) => {
    requestConfirm(
      `Delete integration "${integration.name}"? This cannot be undone.`,
      async () => {
        try {
          await integrationsAPI.delete(integration.id);
          await fetchData();
        } catch (err) {
          console.error('Failed to delete integration:', err);
        }
      }
    );
  };

  if (loading) {
    return (
      <div className="min-h-screen pattern-bg">
        <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen pattern-bg">
      <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8 space-y-6">
        {/* Header */}
        <div className="animate-fade-in">
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center space-x-3">
              <div className="p-3 bg-secondary rounded-xl">
                <SettingsIcon className="w-8 h-8 text-primary" />
              </div>
              <div>
                <h1 className="text-4xl font-bold text-foreground">Settings</h1>
                <p className="text-muted-foreground text-lg">Manage your organization and preferences</p>
              </div>
            </div>
            {isAdminOrOwner && (
              <Link href="/settings/integrations/new">
                <Button className="flex items-center gap-2">
                  <Plus className="w-4 h-4" />
                  Add Integration
                </Button>
              </Link>
            )}
          </div>

        </div>

        {/* OAuth Error */}
        {oauthError && (
          <div className="p-4 bg-destructive/10 text-destructive rounded-lg flex items-center gap-2 animate-fade-in">
            <AlertCircle className="w-5 h-5 flex-shrink-0" />
            {oauthError}
            <Button
              variant="ghost"
              size="sm"
              className="ml-auto"
              onClick={() => setOauthError(null)}
            >
              Dismiss
            </Button>
          </div>
        )}

        {/* Integrations List */}
        <Card className="animate-slide-up">
          <CardHeader className="border-b border-border">
            <CardTitle>Active Integrations</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            {integrations.length === 0 && !(linearStatus?.connected) && !(hubspotStatus?.connected) && !(salesforceStatus?.connected) && !(jiraStatus?.connected) ? (
              <div className="text-center py-12">
                <Settings2 className="w-16 h-16 mx-auto text-muted-foreground/50 mb-4" />
                <h3 className="text-lg font-semibold text-foreground mb-2">No integrations yet</h3>
                <p className="text-muted-foreground mb-6">
                  Connect Slack, Intercom, or other services to receive feedback alerts
                </p>
                {isAdminOrOwner ? (
                  <Link href="/settings/integrations/new">
                    <Button>
                      <Plus className="w-4 h-4 mr-2" />
                      Add Your First Integration
                    </Button>
                  </Link>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Contact an admin to add integrations.
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                {integrations.map(integration => (
                  <div
                    key={integration.id}
                    className="p-4 border border-border rounded-xl bg-card/50 hover:bg-card/80 transition-colors"
                  >
                    <div className="flex items-start justify-between">
                      <Link
                        href={`/settings/integrations/${integration.id}`}
                        className="flex items-center gap-3 flex-1 group"
                      >
                        <div className={`p-2 rounded-lg ${integration.type === 'intercom' ? 'bg-[#1F8DED]/10' : 'bg-secondary'}`}>
                          {integration.type === 'intercom' ? (
                            <IntercomIcon className="w-6 h-6" />
                          ) : (
                            <SlackIcon className="w-6 h-6" />
                          )}
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground group-hover:text-primary transition-colors">
                              {integration.name || 'Unnamed Integration'}
                            </span>
                            {integration.is_active ? (
                              <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                                Active
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-muted-foreground">
                                Disabled
                              </Badge>
                            )}
                            <Badge variant="secondary" className="text-xs flex items-center gap-1">
                              {integration.integration_type === 'oauth' ? (
                                <><LinkIcon className="w-3 h-3" /> OAuth</>
                              ) : (
                                <><Webhook className="w-3 h-3" /> Webhook</>
                              )}
                            </Badge>
                            <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            {integration.team_name && (
                              <span>{integration.team_name}</span>
                            )}
                            {integration.team_name && integration.channel_name && (
                              <span>•</span>
                            )}
                            {integration.channel_name && (
                              <span>#{integration.channel_name}</span>
                            )}
                          </div>
                          {/* Triggers */}
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            {integration.triggers.map(trigger => (
                              <Badge key={trigger} variant="secondary" className="text-xs">
                                {TRIGGER_OPTIONS.find(t => t.value === trigger)?.label || trigger}
                              </Badge>
                            ))}
                          </div>
                        </div>
                      </Link>
                      {isAdminOrOwner && (
                        <div className="flex items-center gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.preventDefault();
                              handleTest(integration);
                            }}
                            disabled={testingId === integration.id}
                            title="Send test message"
                          >
                            {testingId === integration.id ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Send className="w-4 h-4" />
                            )}
                          </Button>
                          <Link href={`/settings/integrations/${integration.id}`}>
                            <Button variant="outline" size="sm" title="Configure">
                              <Settings2 className="w-4 h-4" />
                            </Button>
                          </Link>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={(e) => {
                              e.preventDefault();
                              handleDelete(integration);
                            }}
                            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            title="Delete"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      )}
                    </div>

                    {/* Status info */}
                    <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground ml-11">
                      {integration.last_used_at && (
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          Last used: {new Date(integration.last_used_at).toLocaleString()}
                        </span>
                      )}
                      {integration.error_count > 0 && (
                        <span className="flex items-center gap-1 text-destructive">
                          <AlertCircle className="w-3 h-3" />
                          {integration.error_count} error(s)
                        </span>
                      )}
                    </div>

                    {/* Test result */}
                    {testResult && testResult.id === integration.id && (
                      <div
                        className={`mt-3 p-3 rounded-lg text-sm flex items-center gap-2 ml-11 ${
                          testResult.success
                            ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                            : 'bg-destructive/10 text-destructive'
                        }`}
                      >
                        {testResult.success ? (
                          <CheckCircle className="w-4 h-4 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 flex-shrink-0" />
                        )}
                        {testResult.message}
                      </div>
                    )}
                  </div>
                ))}

                {/* HubSpot CRM — Active Integration Card */}
                {hubspotStatus?.connected && (
                  <div className="p-4 border border-border rounded-xl bg-card/50 hover:bg-card/80 transition-colors">
                    <div className="flex items-start justify-between">
                      <Link
                        href="/settings/integrations/hubspot"
                        className="flex items-center gap-3 flex-1 group"
                      >
                        <div className="p-2 rounded-lg bg-[#FF7A59]/10">
                          {/* HubSpot brand orange icon */}
                          <div className="w-6 h-6 rounded flex items-center justify-center bg-[#FF7A59] text-white text-xs font-bold leading-none">
                            HS
                          </div>
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground group-hover:text-primary transition-colors">
                              HubSpot CRM
                            </span>
                            <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                              Connected
                            </Badge>
                            <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            {hubspotStatus.portal_name && (
                              <span>{hubspotStatus.portal_name}</span>
                            )}
                          </div>
                          {hubspotStatus.token_hint && (
                            <p className="text-xs text-muted-foreground mt-1">
                              Token: {hubspotStatus.token_hint}
                            </p>
                          )}
                        </div>
                      </Link>
                      {isAdminOrOwner && (
                        <div className="flex items-center gap-2 ml-4">
                          <Link href="/settings/integrations/hubspot">
                            <Button variant="outline" size="sm" title="Configure">
                              <Settings2 className="w-4 h-4" />
                            </Button>
                          </Link>
                        </div>
                      )}
                    </div>
                    {hubspotStatus.connected_at && (
                      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground ml-11">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          Connected: {new Date(hubspotStatus.connected_at).toLocaleString()}
                        </span>
                      </div>
                    )}
                  </div>
                )}

                {/* Linear — Active Integration Card */}
                {linearStatus?.connected && (
                  <div className="p-4 border border-border rounded-xl bg-card/50 hover:bg-card/80 transition-colors">
                    <div className="flex items-start justify-between">
                      <Link
                        href="/settings/integrations/linear"
                        className="flex items-center gap-3 flex-1 group"
                      >
                        <div className="p-2 rounded-lg bg-[#5E6AD2]/10">
                          <LinearIcon className="w-6 h-6 text-[#5E6AD2]" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground group-hover:text-primary transition-colors">
                              Linear
                            </span>
                            {linearStatus.is_active ? (
                              <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                                Active
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-muted-foreground">
                                Disconnected
                              </Badge>
                            )}
                            <Badge variant="secondary" className="text-xs flex items-center gap-1">
                              <LinkIcon className="w-3 h-3" /> OAuth
                            </Badge>
                            <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            {linearStatus.org_name && (
                              <span>{linearStatus.org_name}</span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            <Badge variant="secondary" className="text-xs">
                              Issue Tracking
                            </Badge>
                            <Badge variant="secondary" className="text-xs">
                              Status Sync
                            </Badge>
                          </div>
                        </div>
                      </Link>
                      {isAdminOrOwner && (
                        <div className="flex items-center gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={async () => {
                              setLinearTesting(true);
                              setLinearTestResult(null);
                              try {
                                const result = await linearAPI.testConnection();
                                setLinearTestResult(result);
                              } catch (err: any) {
                                setLinearTestResult({
                                  success: false,
                                  message: err.response?.data?.detail || 'Test failed',
                                });
                              } finally {
                                setLinearTesting(false);
                              }
                            }}
                            disabled={linearTesting}
                            title="Test connection"
                          >
                            {linearTesting ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Send className="w-4 h-4" />
                            )}
                          </Button>
                          <Link href="/settings/integrations/linear">
                            <Button variant="outline" size="sm" title="Configure">
                              <Settings2 className="w-4 h-4" />
                            </Button>
                          </Link>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              requestConfirm(
                                'Disconnect Linear? Existing issue links will be preserved.',
                                async () => {
                                  try {
                                    await linearAPI.disconnect();
                                    await fetchData();
                                  } catch (err) {
                                    console.error('Failed to disconnect Linear:', err);
                                  }
                                }
                              );
                            }}
                            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            title="Disconnect"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                    {linearStatus.connected_at && (
                      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground ml-11">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          Connected: {new Date(linearStatus.connected_at).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {linearTestResult && (
                      <div
                        className={`mt-3 p-3 rounded-lg text-sm flex items-center gap-2 ml-11 ${
                          linearTestResult.success
                            ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                            : 'bg-destructive/10 text-destructive'
                        }`}
                      >
                        {linearTestResult.success ? (
                          <CheckCircle className="w-4 h-4 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 flex-shrink-0" />
                        )}
                        {linearTestResult.message}
                      </div>
                    )}
                  </div>
                )}

                {/* Salesforce CRM — Active Integration Card */}
                {salesforceStatus?.connected && (
                  <div className="p-4 border border-border rounded-xl bg-card/50 hover:bg-card/80 transition-colors">
                    <div className="flex items-start justify-between">
                      <Link
                        href="/settings/integrations/salesforce"
                        className="flex items-center gap-3 flex-1 group"
                      >
                        <div className="p-2 rounded-lg bg-[#00A1E0]/10">
                          <SalesforceIcon className="w-6 h-6 text-[#00A1E0]" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground group-hover:text-primary transition-colors">
                              Salesforce
                            </span>
                            <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                              Connected
                            </Badge>
                            <Badge variant="secondary" className="text-xs flex items-center gap-1">
                              <LinkIcon className="w-3 h-3" /> OAuth
                            </Badge>
                            <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            {salesforceStatus.instance_url && (
                              <span>{salesforceStatus.instance_url}</span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            <Badge variant="secondary" className="text-xs">
                              CRM Enrichment
                            </Badge>
                          </div>
                        </div>
                      </Link>
                      {isAdminOrOwner && (
                        <div className="flex items-center gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={async () => {
                              setSalesforceTesting(true);
                              setSalesforceTestResult(null);
                              try {
                                const result = await salesforceAPI.test();
                                setSalesforceTestResult(result);
                              } catch (err: any) {
                                setSalesforceTestResult({
                                  success: false,
                                  message: err.response?.data?.detail || 'Test failed',
                                });
                              } finally {
                                setSalesforceTesting(false);
                              }
                            }}
                            disabled={salesforceTesting}
                            title="Test connection"
                          >
                            {salesforceTesting ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Send className="w-4 h-4" />
                            )}
                          </Button>
                          <Link href="/settings/integrations/salesforce">
                            <Button variant="outline" size="sm" title="Configure">
                              <Settings2 className="w-4 h-4" />
                            </Button>
                          </Link>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              requestConfirm(
                                'Disconnect Salesforce? Existing enrichment data will not be deleted.',
                                async () => {
                                  try {
                                    await salesforceAPI.disconnect();
                                    await fetchData();
                                  } catch (err) {
                                    console.error('Failed to disconnect Salesforce:', err);
                                  }
                                }
                              );
                            }}
                            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            title="Disconnect"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                    {salesforceStatus.connected_at && (
                      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground ml-11">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          Connected: {new Date(salesforceStatus.connected_at).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {salesforceTestResult && (
                      <div
                        className={`mt-3 p-3 rounded-lg text-sm flex items-center gap-2 ml-11 ${
                          salesforceTestResult.success
                            ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                            : 'bg-destructive/10 text-destructive'
                        }`}
                      >
                        {salesforceTestResult.success ? (
                          <CheckCircle className="w-4 h-4 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 flex-shrink-0" />
                        )}
                        {salesforceTestResult.message}
                      </div>
                    )}
                  </div>
                )}

                {/* Jira — Active Integration Card */}
                {jiraStatus?.connected && (
                  <div className="p-4 border border-border rounded-xl bg-card/50 hover:bg-card/80 transition-colors">
                    <div className="flex items-start justify-between">
                      <Link
                        href="/settings/integrations/jira"
                        className="flex items-center gap-3 flex-1 group"
                      >
                        <div className="p-2 rounded-lg bg-[#0052CC]/10">
                          <JiraIcon className="w-6 h-6 text-[#0052CC]" />
                        </div>
                        <div className="flex-1">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-foreground group-hover:text-primary transition-colors">
                              Jira Cloud
                            </span>
                            {jiraStatus.is_active ? (
                              <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950">
                                Active
                              </Badge>
                            ) : (
                              <Badge variant="outline" className="text-muted-foreground">
                                Disconnected
                              </Badge>
                            )}
                            <ChevronRight className="w-4 h-4 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity" />
                          </div>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            {jiraStatus.site_url && (
                              <span>{jiraStatus.site_url}</span>
                            )}
                          </div>
                          <div className="flex flex-wrap gap-1.5 mt-2">
                            <Badge variant="secondary" className="text-xs">
                              Issue Tracking
                            </Badge>
                          </div>
                        </div>
                      </Link>
                      {isAdminOrOwner && (
                        <div className="flex items-center gap-2 ml-4">
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={async () => {
                              setJiraTesting(true);
                              setJiraTestResult(null);
                              try {
                                const result = await jiraAPI.testConnection();
                                setJiraTestResult({ success: result.success, message: result.message ?? '' });
                              } catch (err: any) {
                                setJiraTestResult({
                                  success: false,
                                  message: err.response?.data?.detail || 'Test failed',
                                });
                              } finally {
                                setJiraTesting(false);
                              }
                            }}
                            disabled={jiraTesting}
                            title="Test connection"
                          >
                            {jiraTesting ? (
                              <Loader2 className="w-4 h-4 animate-spin" />
                            ) : (
                              <Send className="w-4 h-4" />
                            )}
                          </Button>
                          <Link href="/settings/integrations/jira">
                            <Button variant="outline" size="sm" title="Configure">
                              <Settings2 className="w-4 h-4" />
                            </Button>
                          </Link>
                          <Button
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              requestConfirm(
                                'Disconnect Jira? Existing linked issues will be preserved.',
                                async () => {
                                  try {
                                    await jiraAPI.disconnect();
                                    await fetchData();
                                  } catch (err) {
                                    console.error('Failed to disconnect Jira:', err);
                                  }
                                }
                              );
                            }}
                            className="text-destructive hover:bg-destructive hover:text-destructive-foreground"
                            title="Disconnect"
                          >
                            <Trash2 className="w-4 h-4" />
                          </Button>
                        </div>
                      )}
                    </div>
                    {jiraStatus.connected_at && (
                      <div className="flex items-center gap-4 mt-3 text-xs text-muted-foreground ml-11">
                        <span className="flex items-center gap-1">
                          <Clock className="w-3 h-3" />
                          Connected: {new Date(jiraStatus.connected_at).toLocaleString()}
                        </span>
                      </div>
                    )}

                    {jiraTestResult && (
                      <div
                        className={`mt-3 p-3 rounded-lg text-sm flex items-center gap-2 ml-11 ${
                          jiraTestResult.success
                            ? 'bg-green-50 dark:bg-green-950 text-green-700 dark:text-green-300'
                            : 'bg-destructive/10 text-destructive'
                        }`}
                      >
                        {jiraTestResult.success ? (
                          <CheckCircle className="w-4 h-4 flex-shrink-0" />
                        ) : (
                          <XCircle className="w-4 h-4 flex-shrink-0" />
                        )}
                        {jiraTestResult.message}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Available Integrations */}
        <Card className="animate-slide-up stagger-1">
          <CardHeader className="border-b border-border">
            <CardTitle>Available Integrations</CardTitle>
          </CardHeader>
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Slack - Available */}
              <Link href="/settings/integrations/new">
                <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-[#4A154B]/10 rounded-lg">
                      <SlackIcon className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Slack</span>
                        <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                          Available
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Get feedback alerts in your Slack channels
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                </div>
              </Link>

              {/* Webhooks - Available */}
              <Link href="/settings/integrations/new">
                <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 rounded-lg">
                      <Webhook className="w-6 h-6 text-primary" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Webhooks</span>
                        <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                          Available
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Send feedback data to your own endpoints
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                </div>
              </Link>

              {/* Intercom - Available */}
              <Link href="/settings/integrations/new?type=intercom">
                <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-[#1F8DED]/10 rounded-lg">
                      <IntercomIcon className="w-6 h-6" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Intercom</span>
                        <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                          Available
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Analyze support conversations with AI
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                </div>
              </Link>

              {/* HubSpot CRM - Available (only shown when not connected) */}
              {!hubspotStatus?.connected && (
                <Link href="/settings/integrations/hubspot">
                  <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-[#FF7A59]/10 rounded-lg">
                        <div className="w-6 h-6 rounded flex items-center justify-center bg-[#FF7A59] text-white text-xs font-bold leading-none">
                          HS
                        </div>
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground group-hover:text-primary transition-colors">HubSpot CRM</span>
                          <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                            Available
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Enrich customer profiles with CRM data
                        </p>
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </Link>
              )}

              {/* Linear - Available (only shown when not connected) */}
              {!linearStatus?.connected && (
                <Link href="/settings/integrations/linear">
                  <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-[#5E6AD2]/10 rounded-lg">
                        <LinearIcon className="w-6 h-6 text-[#5E6AD2]" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Linear</span>
                          <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                            Available
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Create issues directly from feedback
                        </p>
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </Link>
              )}

              {/* Salesforce CRM - Available (only shown when not connected) */}
              {!salesforceStatus?.connected && (
                <Link href="/settings/integrations/salesforce">
                  <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-[#00A1E0]/10 rounded-lg">
                        <SalesforceIcon className="w-6 h-6 text-[#00A1E0]" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Salesforce</span>
                          <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                            Available
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Enrich customer profiles with CRM data
                        </p>
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </Link>
              )}

              {/* Jira Cloud - Available (only shown when not connected) */}
              {!jiraStatus?.connected && (
                <Link href="/settings/integrations/jira">
                  <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-[#0052CC]/10 rounded-lg">
                        <JiraIcon className="w-6 h-6 text-[#0052CC]" />
                      </div>
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Jira Cloud</span>
                          <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                            Available
                          </Badge>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          Create issues directly from feedback
                        </p>
                      </div>
                      <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                    </div>
                  </div>
                </Link>
              )}

              {/* Usage Events - Available */}
              <Link href="/settings/usage-events">
                <div className="p-4 border border-border rounded-xl hover:border-primary/50 hover:bg-secondary/30 transition-all cursor-pointer group">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-primary/10 rounded-lg">
                      <Activity className="w-6 h-6 text-primary" />
                    </div>
                    <div className="flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-foreground group-hover:text-primary transition-colors">Usage Events</span>
                        <Badge variant="outline" className="text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950 text-xs">
                          Available
                        </Badge>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        Ingest product usage events to enrich Customer 360 and health scores
                      </p>
                    </div>
                    <ChevronRight className="w-5 h-5 text-muted-foreground group-hover:text-primary transition-colors" />
                  </div>
                </div>
              </Link>

              {/* Discord - Coming Soon */}
              <div className="p-4 border border-border rounded-xl bg-muted/30 opacity-60 cursor-not-allowed">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-[#5865F2]/10 rounded-lg">
                    <MessageSquare className="w-6 h-6 text-[#5865F2]" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">Discord</span>
                      <Badge variant="secondary" className="text-xs">
                        Coming Soon
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Get alerts in your Discord server
                    </p>
                  </div>
                </div>
              </div>

              {/* Microsoft Teams - Coming Soon */}
              <div className="p-4 border border-border rounded-xl bg-muted/30 opacity-60 cursor-not-allowed">
                <div className="flex items-center gap-3">
                  <div className="p-2 bg-[#6264A7]/10 rounded-lg">
                    <Users className="w-6 h-6 text-[#6264A7]" />
                  </div>
                  <div className="flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-foreground">Microsoft Teams</span>
                      <Badge variant="secondary" className="text-xs">
                        Coming Soon
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      Receive feedback alerts in Teams channels
                    </p>
                  </div>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      </main>

      {/* Confirm Dialog */}
      <Dialog open={!!confirmAction} onOpenChange={(open) => { if (!open) setConfirmAction(null); }}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Confirm Action</DialogTitle>
            <DialogDescription>{confirmMessage}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmAction(null)}>Cancel</Button>
            <Button variant="destructive" onClick={() => { confirmAction?.(); setConfirmAction(null); }}>Confirm</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function IntegrationsPage() {
  return (
    <Suspense fallback={
      <div className="min-h-screen pattern-bg">
        <main className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-muted-foreground" />
          </div>
        </main>
      </div>
    }>
      <IntegrationsContent />
    </Suspense>
  );
}
