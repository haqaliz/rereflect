'use client';

import { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AlertCircle,
  CheckCircle,
  ExternalLink,
  Loader2,
  Link as LinkIcon,
} from 'lucide-react';
import {
  linearAPI,
  LinearConnectionStatus,
  LinearTeam,
  LinearTeamMapping,
  LinearStatusMapping,
  REREFLECT_CATEGORIES,
  LINEAR_STATUS_TYPES,
  REREFLECT_STATUSES,
} from '@/lib/api/linear';
import { useAuth } from '@/contexts/AuthContext';

export function LinearSettings() {
  const { user } = useAuth();
  const [status, setStatus] = useState<LinearConnectionStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [disconnecting, setDisconnecting] = useState(false);
  const [teams, setTeams] = useState<LinearTeam[]>([]);
  const [teamMappings, setTeamMappings] = useState<LinearTeamMapping[]>([]);
  const [statusMappings, setStatusMappings] = useState<LinearStatusMapping[]>([]);
  const [savingTeamMappings, setSavingTeamMappings] = useState(false);
  const [savingStatusMappings, setSavingStatusMappings] = useState(false);

  const isAdminOrOwner = user?.role === 'owner' || user?.role === 'admin';

  const fetchStatus = useCallback(async () => {
    try {
      const s = await linearAPI.getStatus();
      setStatus(s);
      return s;
    } catch {
      // ignore
    }
  }, []);

  const fetchMappings = useCallback(async () => {
    try {
      const [tm, sm] = await Promise.all([
        linearAPI.getTeamMappings(),
        linearAPI.getStatusMappings(),
      ]);
      setTeamMappings(tm);
      setStatusMappings(sm);
    } catch {
      // ignore
    }
  }, []);

  const fetchTeams = useCallback(async () => {
    try {
      const t = await linearAPI.getTeams();
      setTeams(t);
    } catch {
      // ignore
    }
  }, []);

  useEffect(() => {
    async function init() {
      setLoading(true);
      const s = await fetchStatus();
      if (s?.connected) {
        await Promise.all([fetchTeams(), fetchMappings()]);
      }
      setLoading(false);
    }
    init();
  }, [fetchStatus, fetchTeams, fetchMappings]);

  const handleConnect = async () => {
    try {
      const { auth_url } = await linearAPI.getConnectUrl();
      window.location.href = auth_url;
    } catch {
      // ignore
    }
  };

  const handleDisconnect = async () => {
    if (!confirm('Disconnect Linear? Existing issue links will be preserved.')) return;
    setDisconnecting(true);
    try {
      await linearAPI.disconnect();
      const s = await fetchStatus();
      if (!s?.connected) {
        setTeams([]);
        setTeamMappings([]);
        setStatusMappings([]);
      }
    } catch {
      // ignore
    } finally {
      setDisconnecting(false);
    }
  };

  const handleTeamMappingChange = (category: string, teamId: string) => {
    const team = teams.find(t => t.id === teamId);
    if (!team) return;
    setTeamMappings(prev => {
      const existing = prev.find(m => m.rereflect_category === category);
      if (existing) {
        return prev.map(m =>
          m.rereflect_category === category
            ? { ...m, linear_team_id: teamId, linear_team_name: team.name }
            : m
        );
      }
      return [
        ...prev,
        {
          id: Date.now(),
          rereflect_category: category,
          linear_team_id: teamId,
          linear_team_name: team.name,
          linear_project_id: null,
          linear_project_name: null,
          priority: 1,
        },
      ];
    });
  };

  const handleSaveTeamMappings = async () => {
    setSavingTeamMappings(true);
    try {
      const updated = await linearAPI.updateTeamMappings({
        mappings: teamMappings.map(m => ({
          rereflect_category: m.rereflect_category,
          linear_team_id: m.linear_team_id,
          linear_team_name: m.linear_team_name,
          linear_project_id: m.linear_project_id ?? undefined,
          linear_project_name: m.linear_project_name ?? undefined,
          priority: m.priority,
        })),
      });
      setTeamMappings(updated);
    } catch {
      // ignore
    } finally {
      setSavingTeamMappings(false);
    }
  };

  const handleStatusMappingChange = (statusType: string, rereflectStatus: string) => {
    setStatusMappings(prev => {
      const existing = prev.find(m => m.linear_status_type === statusType);
      const typeDef = LINEAR_STATUS_TYPES.find(t => t.value === statusType);
      if (existing) {
        return prev.map(m =>
          m.linear_status_type === statusType
            ? { ...m, rereflect_status: rereflectStatus }
            : m
        );
      }
      return [
        ...prev,
        {
          id: Date.now(),
          linear_status_name: typeDef?.label ?? statusType,
          linear_status_type: statusType,
          rereflect_status: rereflectStatus,
        },
      ];
    });
  };

  const handleSaveStatusMappings = async () => {
    setSavingStatusMappings(true);
    try {
      const updated = await linearAPI.updateStatusMappings({
        mappings: statusMappings.map(m => ({
          linear_status_name: m.linear_status_name,
          linear_status_type: m.linear_status_type,
          rereflect_status: m.rereflect_status,
        })),
      });
      setStatusMappings(updated);
    } catch {
      // ignore
    } finally {
      setSavingStatusMappings(false);
    }
  };

  if (loading) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center py-12">
          <Loader2 className="w-6 h-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  const isConnected = status?.connected ?? false;
  const isActive = status?.is_active ?? false;
  const showBanner = isConnected && !isActive;

  return (
    <div className="space-y-4">
      {/* Disconnection banner */}
      {showBanner && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Linear connection lost. Existing issue links are preserved. Reconnect to resume sync.
          </AlertDescription>
        </Alert>
      )}

      {/* Connection card */}
      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2">
            <LinkIcon className="w-5 h-5" />
            Linear Integration
          </CardTitle>
        </CardHeader>
        <CardContent className="pt-6">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              {isConnected ? (
                <>
                  <div className="flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-green-600" />
                    <span className="font-semibold">{status?.org_name}</span>
                    <Badge
                      variant="outline"
                      className={
                        isActive
                          ? 'text-green-600 border-green-600/30 bg-green-50 dark:bg-green-950'
                          : 'text-muted-foreground'
                      }
                    >
                      {isActive ? 'Connected' : 'Disconnected'}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Connected by {status?.connected_by_email}
                    {status?.connected_at && (
                      <> on {new Date(status.connected_at).toLocaleDateString()}</>
                    )}
                  </p>
                </>
              ) : (
                <p className="text-muted-foreground">
                  Connect Linear to create issues directly from feedback
                </p>
              )}
            </div>
            {isAdminOrOwner && (
              <div className="flex items-center gap-2">
                {isConnected ? (
                  <>
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={handleConnect}
                      className="flex items-center gap-1"
                    >
                      <ExternalLink className="w-4 h-4" />
                      Reconnect
                    </Button>
                    <Button
                      variant="destructive"
                      size="sm"
                      onClick={handleDisconnect}
                      disabled={disconnecting}
                    >
                      {disconnecting ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        'Disconnect'
                      )}
                    </Button>
                  </>
                ) : (
                  <Button onClick={handleConnect} className="flex items-center gap-2">
                    Connect Linear
                  </Button>
                )}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Mapping config — only shown when connected and active */}
      {isConnected && isActive && (
        <Card>
          <CardContent className="pt-6">
            <Tabs defaultValue="team-mapping">
              <TabsList className="mb-6">
                <TabsTrigger value="team-mapping">Team Mapping</TabsTrigger>
                <TabsTrigger value="status-mapping">Status Mapping</TabsTrigger>
              </TabsList>

              {/* Team Mapping Tab */}
              <TabsContent value="team-mapping" className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Map Rereflect categories to Linear teams. When creating an issue, the matching team will be pre-selected.
                </p>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Category</th>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Linear Team</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {REREFLECT_CATEGORIES.map(cat => {
                        const mapping = teamMappings.find(m => m.rereflect_category === cat.value);
                        return (
                          <tr key={cat.value}>
                            <td className="px-4 py-3 font-medium">{cat.label}</td>
                            <td className="px-4 py-3">
                              <Select
                                value={mapping?.linear_team_id ?? ''}
                                onValueChange={val => handleTeamMappingChange(cat.value, val)}
                                disabled={!isAdminOrOwner}
                              >
                                <SelectTrigger className="w-48">
                                  <SelectValue placeholder="Select team…" />
                                </SelectTrigger>
                                <SelectContent>
                                  {teams.map(team => (
                                    <SelectItem key={team.id} value={team.id}>
                                      {team.name}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {isAdminOrOwner && (
                  <div className="flex justify-end">
                    <Button onClick={handleSaveTeamMappings} disabled={savingTeamMappings}>
                      {savingTeamMappings ? (
                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
                      ) : (
                        'Save Team Mappings'
                      )}
                    </Button>
                  </div>
                )}
              </TabsContent>

              {/* Status Mapping Tab */}
              <TabsContent value="status-mapping" className="space-y-4">
                <p className="text-sm text-muted-foreground">
                  Map Linear status types to Rereflect workflow statuses. Status changes in Linear will update feedback automatically.
                </p>
                <div className="border border-border rounded-lg overflow-hidden">
                  <table className="w-full text-sm">
                    <thead className="bg-muted/50">
                      <tr>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Linear Status Type</th>
                        <th className="text-left px-4 py-3 font-medium text-muted-foreground">Rereflect Status</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      {LINEAR_STATUS_TYPES.map(statusType => {
                        const mapping = statusMappings.find(m => m.linear_status_type === statusType.value);
                        return (
                          <tr key={statusType.value}>
                            <td className="px-4 py-3 font-medium">{statusType.label}</td>
                            <td className="px-4 py-3">
                              <Select
                                value={mapping?.rereflect_status ?? ''}
                                onValueChange={val => handleStatusMappingChange(statusType.value, val)}
                                disabled={!isAdminOrOwner}
                              >
                                <SelectTrigger className="w-40">
                                  <SelectValue placeholder="Select status…" />
                                </SelectTrigger>
                                <SelectContent>
                                  {REREFLECT_STATUSES.map(s => (
                                    <SelectItem key={s.value} value={s.value}>
                                      {s.label}
                                    </SelectItem>
                                  ))}
                                </SelectContent>
                              </Select>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {isAdminOrOwner && (
                  <div className="flex justify-end">
                    <Button onClick={handleSaveStatusMappings} disabled={savingStatusMappings}>
                      {savingStatusMappings ? (
                        <><Loader2 className="w-4 h-4 mr-2 animate-spin" />Saving…</>
                      ) : (
                        'Save Status Mappings'
                      )}
                    </Button>
                  </div>
                )}
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
