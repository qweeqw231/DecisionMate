//src/main/ets/common/Constants.ets
import preferences from '@ohos.data.preferences';

export class Constants {
  static readonly DEFAULT_BASE_URL: string = 'http://10.31.117.54:8000';
  static readonly API_DECISION: string = '/api/decision';
  static readonly PREF_NAME: string = 'decision_mate_settings';

  /**
   * 获取当前配置的后端地址
   */
  static async getBaseUrl(): Promise<string> {
    try {
      const prefs = await preferences.getPreferences(getContext(), Constants.PREF_NAME);
      const savedUrl = await prefs.get('base_url', Constants.DEFAULT_BASE_URL) as string;
      return savedUrl;
    } catch (err) {
      return Constants.DEFAULT_BASE_URL;
    }
  }
}