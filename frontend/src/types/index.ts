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
  front_photo_url: string | null;
  side_photo_url: string | null;
}

export interface UserScore {
  dimension: Dimension;
  score: number;
  streak_days: number;
}

export interface Task {
  id: string;
  dimension: Dimension;
  title: string;
  description: string;
  difficulty: 'easy' | 'medium' | 'hard';
  scheduled_date: string;
  status: 'pending' | 'in_progress' | 'completed' | 'failed';
  completed_at: string | null;
}

export interface Conversation {
  id: string;
  role: 'system' | 'user';
  content: string;
  created_at: string;
}

export interface ScoreHistory {
  dimension: Dimension;
  delta: number;
  reason: string;
  created_at: string;
}
