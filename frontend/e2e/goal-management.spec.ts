import { expect, test } from '@playwright/test';

test('a goal can be paused and edited without disappearing', async ({ page }) => {
  const now = '2026-08-12T00:00:00+00:00';
  let goal = {
    id: 'goal-1',
    user_id: 'user-1',
    content: '每天晚上8点在跑步机上爬坡走40分钟',
    goal_type: 'exercise',
    target_metric: null,
    target_value: null,
    current_value: null,
    progress_mode: 'sessions',
    completed_sessions: 2,
    last_progress_at: now,
    deadline: null,
    milestones: [],
    importance_score: 0.5,
    status: 'active',
    source: 'chat',
    created_at: now,
    updated_at: now,
    recurrence: 'daily',
    days_of_week: [],
    preferred_time: '20:00',
    duration_minutes: 40,
    start_date: null,
    reminder_enabled: true,
    reminder_minutes_before: 30,
  };

  await page.route('**/api/**', async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === '/api/auth/refresh') {
      await route.fulfill({ json: { access_token: 'test-token', token_type: 'bearer' } });
      return;
    }
    if (path === '/api/users/me') {
      await route.fulfill({ json: { id: 'user-1', email: 'user@example.com', nickname: '测试用户', avatar_url: null } });
      return;
    }
    if (path === '/api/users/me/profile') {
      await route.fulfill({ json: { height_cm: 175, weight_kg: 70, age: 25, gender: 'male', body_fat_pct: null, avatar_url: null, front_photo_url: null, side_photo_url: null, notification_settings: {} } });
      return;
    }
    if (path === '/api/notifications') {
      await route.fulfill({ json: { items: [], unread_count: 0 } });
      return;
    }
    if (path === '/api/goals' && request.method() === 'GET') {
      await route.fulfill({ json: [goal] });
      return;
    }
    if (path === '/api/goals/progress/summary') {
      await route.fulfill({ json: { 'goal-1': { goal_id: 'goal-1', content: goal.content, goal_type: 'exercise', period_start: '2026-08-10', period_end: '2026-08-16', scheduled_total: 7, scheduled_to_date: 3, completed: 2, remaining_to_date: 1, adherence: 66.7, completed_sessions: 2, current_value: 2, target_value: null, progress_mode: 'sessions' } } });
      return;
    }
    if (path === '/api/goals/goal-1/progress') {
      await route.fulfill({ json: [{ id: 'event-1', event_type: 'task_completed', delta: 1, previous_value: 1, current_value: 2, event_date: '2026-08-12', source: 'task_completion', metadata: { task_title: '跑步机爬坡走40分钟' }, created_at: now }] });
      return;
    }
    if (path === '/api/goals/goal-1' && request.method() === 'PUT') {
      goal = { ...goal, ...(request.postDataJSON() as Partial<typeof goal>), updated_at: now };
      await route.fulfill({ json: goal });
      return;
    }
    await route.fulfill({ status: 404, json: { detail: `Unhandled test API: ${path}` } });
  });

  await page.goto('/goals');
  await expect(page.getByRole('heading', { name: '成长目标' })).toBeVisible();
  await expect(page.getByText(goal.content)).toBeVisible();
  await expect(page.getByText('2/3 次')).toBeVisible();
  await page.getByRole('button', { name: '执行记录' }).click();
  const timeline = page.getByRole('dialog', { name: '目标执行记录' });
  await expect(timeline.getByText('跑步机爬坡走40分钟')).toBeVisible();
  await timeline.getByRole('button', { name: '×' }).click();

  await page.getByRole('button', { name: '暂停', exact: true }).click();
  await expect(page.getByText('已暂停', { exact: true })).toBeVisible();
  await expect(page.getByText(goal.content)).toBeVisible();

  await page.getByRole('button', { name: '编辑' }).click();
  const dialog = page.getByRole('dialog', { name: '编辑成长目标' });
  await expect(dialog).toBeVisible();
  await dialog.getByLabel('目标内容').fill('每晚20:00跑步机爬坡走45分钟');
  await dialog.getByRole('button', { name: '保存修改' }).click();

  await expect(page.getByText('每晚20:00跑步机爬坡走45分钟')).toBeVisible();
  await expect(dialog).toBeHidden();
});
