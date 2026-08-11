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
    deadline: null,
    milestones: [],
    importance_score: 0.5,
    status: 'active',
    source: 'chat',
    created_at: now,
    updated_at: now,
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
