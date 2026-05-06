import { motion } from 'framer-motion';

export default function Settings() {
  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-2xl mx-auto">
        <h1 className="text-2xl font-bold text-white mb-6">设置</h1>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800 mb-6">
          <h2 className="text-lg text-slate-300 mb-4">通知设置</h2>
          <div className="space-y-3">
            <div className="flex justify-between items-center">
              <span className="text-slate-400 text-sm">每日任务推送</span>
              <div className="w-10 h-6 bg-blue-600 rounded-full relative cursor-pointer">
                <div className="w-4 h-4 bg-white rounded-full absolute top-1 right-1"></div>
              </div>
            </div>
            <div className="flex justify-between items-center">
              <span className="text-slate-400 text-sm">评分变动提醒</span>
              <div className="w-10 h-6 bg-blue-600 rounded-full relative cursor-pointer">
                <div className="w-4 h-4 bg-white rounded-full absolute top-1 right-1"></div>
              </div>
            </div>
          </div>
        </motion.div>

        <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.1 }}
          className="bg-slate-900 rounded-2xl p-6 border border-slate-800">
          <h2 className="text-lg text-slate-300 mb-4">关于系统</h2>
          <div className="space-y-2 text-sm text-slate-500">
            <p>版本：1.0.0</p>
            <p>灵感来源于小说中的成长系统</p>
            <p>帮助你通过每日任务持续提升自己</p>
          </div>
        </motion.div>
      </div>
    </div>
  );
}
