export type Dimension = 'exercise' | 'diet' | 'sleep' | 'appearance';

export interface User {
  id: string;
  email: string;
  nickname: string;
  avatar_url: string | null;
}

export interface UserProfile {
  height_cm: number | null;
  weight_kg: number | null;
  age: number | null;
  gender: 'male' | 'female' | 'other' | null;
  body_fat_pct: number | null;
  avatar_url: string | null;
  front_photo_url: string | null;
  side_photo_url: string | null;
  daily_task_budget?: number;
  memory_enabled?: number;
  notification_settings?: Record<string, boolean>;
}

export interface UserScore {
  dimension: Dimension;
  score: number;
  baseline_score: number;
  streak_days: number;
}

export interface AssessmentEvidenceComponent {
  key?: string;
  label: string;
  answer: string;
  score: number | null;
  weight: number;
}

export interface AssessmentRun {
  id: string;
  input_hash: string;
  rubric_version: string;
  mode: 'rules';
  scores: Record<Dimension, number>;
  evidence: Record<Dimension, {
    source: string;
    components: AssessmentEvidenceComponent[];
  }>;
  confidence: Record<Dimension, number>;
  overall_confidence: number;
  warnings: string[];
  skin_source: string;
  reused: boolean;
  generation: {
    assessment_id: string;
    status: 'pending' | 'running' | 'completed' | 'failed';
    stage: 'queued' | 'care_suggestions' | 'daily_tasks' | 'completed' | 'failed';
    error: string | null;
    care_suggestions: string[];
    started_at: string | null;
    completed_at: string | null;
  };
  created_at: string;
}

export interface Task {
  id: string;
  goal_id?: string | null;
  dimension: Dimension;
  title: string;
  description: string;
  difficulty: 'easy' | 'medium' | 'hard';
  scheduled_date: string;
  scheduled_time?: string | null;
  source?: 'adaptive' | 'goal' | 'chat_modified';
  status: 'pending' | 'in_progress' | 'completed' | 'failed' | 'deferred';
  completed_at: string | null;
  rationale?: string | null;
  estimated_minutes?: string | null;
  user_feedback?: 'too_easy' | 'just_right' | 'too_hard' | 'not_suitable' | null;
  disposition?: 'snoozed' | 'excused' | 'rescheduled' | 'skipped' | 'expired' | null;
  disposition_reason?: string | null;
  deferred_until?: string | null;
  defer_count?: number;
  original_scheduled_date?: string | null;
  adaptation_metadata?: Record<string, unknown>;
}

export interface UserNotification {
  id: string;
  kind: 'task_reminder' | 'daily_tasks' | 'weekly_review' | 'system';
  title: string;
  message: string;
  payload: { link?: string; task_id?: string; [key: string]: unknown };
  read_at: string | null;
  created_at: string;
}

export interface NotificationInboxResponse {
  items: UserNotification[];
  unread_count: number;
}

export interface BehaviorDimensionMetric {
  baseline: number;
  adherence_7d: number | null;
  adherence_28d: number | null;
  sample_count_7d: number;
  sample_count_28d: number;
  confidence: 'none' | 'low' | 'medium' | 'high';
  momentum: number | null;
  streak_days: number;
}

export interface BehaviorMetrics {
  overall: {
    adherence_7d: number | null;
    adherence_28d: number | null;
    sample_count_7d: number;
    sample_count_28d: number;
    confidence: 'none' | 'low' | 'medium' | 'high';
    momentum: number | null;
  };
  dimensions: Record<Dimension, BehaviorDimensionMetric>;
}

export interface DailyCheckIn {
  id: string;
  date: string;
  sleep_hours: number | null;
  energy: number;
  mood: number;
  stress: number;
  available_minutes: number;
  note: string | null;
}

export interface WeeklyReview {
  id: string;
  week_start: string;
  summary: {
    week_start: string;
    week_end: string;
    completed_tasks: number;
    planned_tasks: number;
    excused_tasks?: number;
    rescheduled_tasks?: number;
    expired_tasks?: number;
    skipped_tasks?: number;
    dimension_adherence: Partial<Record<Dimension, number>>;
    checkin_days: number;
    average_energy: number | null;
    average_stress: number | null;
    suggested_focus: Dimension | null;
    goal_progress: GoalProgressSummary[];
    goal_scheduled: number;
    goal_completed: number;
    goal_adherence: number | null;
  };
  next_week_plan: Record<string, unknown>;
  confirmed: boolean;
}

export interface Goal {
  id: string;
  content: string;
  goal_type: Dimension;
  target_metric: string | null;
  target_value: number | null;
  current_value: number | null;
  progress_mode: 'sessions' | 'manual';
  completed_sessions: number;
  last_progress_at: string | null;
  deadline: string | null;
  milestones: Array<{ title?: string; completed?: boolean }>;
  recurrence: 'flexible' | 'daily' | 'weekly' | 'custom';
  days_of_week: number[];
  preferred_time: string | null;
  duration_minutes: number | null;
  start_date: string | null;
  reminder_enabled: boolean;
  reminder_minutes_before: number;
  status: 'active' | 'completed' | 'paused';
  source: 'manual' | 'chat';
  created_at: string;
}

export interface GoalProgressSummary {
  goal_id: string;
  content: string;
  goal_type: Dimension;
  period_start: string;
  period_end: string;
  scheduled_total: number;
  scheduled_to_date: number;
  completed: number;
  remaining_to_date: number;
  adherence: number | null;
  completed_sessions: number;
  current_value: number | null;
  target_value: number | null;
  progress_mode: 'sessions' | 'manual';
}

export interface GoalProgressEvent {
  id: string;
  event_type: 'task_completed' | 'manual_progress';
  delta: number;
  previous_value: number | null;
  current_value: number | null;
  event_date: string;
  source: string;
  metadata: { task_title?: string; dimension?: Dimension; [key: string]: unknown };
  created_at: string;
}

export interface Conversation {
  id: string;
  role: 'system' | 'user';
  content: string;
  created_at: string;
  metadata?: {
    agent_run?: AgentRunMetadata;
    message_type?: 'profile_assessment' | 'daily_tasks' | 'skin_analysis';
    assessment?: Record<string, unknown>;
    skin_analysis?: Record<string, unknown> | null;
    care_suggestions?: string[];
    greeting?: string;
    scheduled_date?: string;
    tasks?: Array<Record<string, unknown>>;
    [key: string]: unknown;
  };
}

export interface ScoreHistory {
  dimension: Dimension;
  delta: number;
  reason: string;
  created_at: string;
}

export type AgentTraceType =
  | 'status'
  | 'plan'
  | 'tool_call'
  | 'tool_result'
  | 'guardrail'
  | 'error';

export interface AgentTraceEvent {
  type: AgentTraceType;
  title: string;
  detail: string;
  step: number;
  tool?: string | null;
  success?: boolean | null;
  duration_ms?: number | null;
}

export interface AgentMetrics {
  planner_calls?: number;
  tool_calls?: number;
  steps?: number;
  planning_duration_ms?: number;
  response_duration_ms?: number;
  status?: string;
  input_tokens?: number;
  output_tokens?: number;
  estimated_cost?: number;
  models?: string[];
  llm_calls?: number;
}

export interface PendingAction {
  action_id: string;
  tool: string;
  arguments: Record<string, unknown>;
  expires_at: string;
  status: 'pending' | 'approved' | 'rejected' | 'expired' | 'failed';
}

export interface AgentRunMetadata {
  run_id?: string;
  trace: AgentTraceEvent[];
  metrics?: AgentMetrics;
  pending_action?: PendingAction | null;
}
