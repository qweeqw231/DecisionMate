//src/main/ets/services/DecisionService.ets
import http from '@ohos.net.http';
import { DecisionReport, DecisionRequest } from '../models/DecisionModels';
import { Constants } from '../common/Constants';
import { ConversationItem, MessageItem } from '../models/DecisionModels';
import { ArchiveReport } from '../models/DecisionModels';
import { PersonaItem } from '../models/DecisionModels';
import { ActivatedPersona } from '../models/DecisionModels';


export async function analyzeDecision(scenario: string): Promise<DecisionReport> {
  const baseUrl: string = await Constants.getBaseUrl();
  const url: string = baseUrl + Constants.API_DECISION;
  const requestBody: DecisionRequest = { scenario: scenario };
  const httpRequest = http.createHttp();

  try {
    const response = await httpRequest.request(url, {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: JSON.stringify(requestBody),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 10000,
      readTimeout: 30000
    });

    if (response.responseCode === 200) {
      const resultStr: string = response.result as string;
      const resultObj: DecisionReport = JSON.parse(resultStr) as DecisionReport;
      return resultObj;
    } else {
      throw new Error('Server error: ' + response.responseCode.toString());
    }
  } catch (err) {
    console.error('analyzeDecision error:', JSON.stringify(err));
    // 将任意类型的 err 转换为 Error 对象再抛出
    const errorMessage: string = (err instanceof Object) && (err as Record<string, Object>).message
      ? (err as Record<string, string>).message as string
      : 'Network request failed';
    throw new Error(errorMessage);
  } finally {
    httpRequest.destroy();
  }
}

// ==========================================
// Phase 3.2 新增：对话管理API
// ==========================================

export async function createConversation(title?: string): Promise<ConversationItem> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const body = title ? JSON.stringify({ title: title }) : '{}';
    const response = await httpRequest.request(baseUrl + '/api/conversations', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: body,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as ConversationItem;
    }
    throw new Error('Create failed');
  } finally {
    httpRequest.destroy();
  }
}

export async function getConversations(): Promise<ConversationItem[]> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations', {
      method: http.RequestMethod.GET,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as ConversationItem[];
    }
    return [];
  } finally {
    httpRequest.destroy();
  }
}

export async function renameConversation(convId: number, newTitle: string): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId, {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: JSON.stringify({ title: newTitle }),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}

export async function togglePinConversation(convId: number): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId + '/pin', {
      method: http.RequestMethod.POST,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}

export async function deleteConversation(convId: number): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId, {
      method: http.RequestMethod.DELETE,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}

export async function clearAllConversations(): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations', {
      method: http.RequestMethod.DELETE,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}

class SendMessageBody {
  scenario: string = '';
  activated_personas?: ActivatedPersona[];
}

export async function sendMessage(convId: number, scenario: string,activatedPersonas?: ActivatedPersona[]): Promise<DecisionReport> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const body = new SendMessageBody();
    body.scenario = scenario;
    if (activatedPersonas && activatedPersonas.length > 0) {
      body.activated_personas = activatedPersonas;
    }
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId + '/messages', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: JSON.stringify(body ),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 10000,
      readTimeout: 60000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as DecisionReport;
    }
    throw new Error('Send message failed');
  } finally {
    httpRequest.destroy();
  }
}

export async function getMessages(convId: number): Promise<MessageItem[]> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId + '/messages', {
      method: http.RequestMethod.GET,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as MessageItem[];
    }
    return [];
  } finally {
    httpRequest.destroy();
  }
}


export async function submitFeedback(convId: number, msgId: number, feedbackType: string, feedbackText?: string): Promise<ArchiveReport> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const body = JSON.stringify({ feedback_type: feedbackType, feedback_text: feedbackText || '' });
    console.log('submitFeedback url: ' + baseUrl + '/api/conversations/' + convId + '/messages/' + msgId + '/feedback');
    console.log('submitFeedback body: ' + body);

    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId + '/messages/' + msgId + '/feedback', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: body,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });

    console.log('submitFeedback response code: ' + response.responseCode);

    if (response.responseCode === 200) {
      const resultStr: string = response.result as string;
      console.log('submitFeedback response body: ' + resultStr);
      const result: Record<string, Object> = JSON.parse(resultStr) as Record<string, Object>;
      if (result['archive_report']) {
        return result['archive_report'] as ArchiveReport;
      }
      throw new Error('Invalid feedback response');
    }
    // 返回完整的错误信息
    throw new Error('服务器错误: ' + response.responseCode + ', body: ' + (response.result as string));
  } catch (err) {
    console.error('submitFeedback error: ' + JSON.stringify(err));
    // 直接重新抛出，让 InputPage 的 AlertDialog 显示真实错误
    throw new Error('提交失败: ' + (err instanceof Object ? JSON.stringify(err) : String(err)));
  } finally {
    httpRequest.destroy();
  }
}


export async function addUserFactor(factorName: string, value: number, basis: string): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const body = JSON.stringify({ factor_name: factorName, value: value, basis: basis });
    const response = await httpRequest.request(baseUrl + '/api/user-profile/add-factor', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: body,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}


// ==========================================
// Phase 4.2 新增：分身管理 API
// ==========================================

export async function getPersonas(): Promise<PersonaItem[]> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/personas', {
      method: http.RequestMethod.GET,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as PersonaItem[];
    }
    return [];
  } finally {
    httpRequest.destroy();
  }
}

export async function createPersona(name: string, riskPreference: string, corePrinciple?: string): Promise<PersonaItem | null> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const body = JSON.stringify({ name: name, risk_preference: riskPreference, core_principle: corePrinciple || '' });
    const response = await httpRequest.request(baseUrl + '/api/personas', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: body,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as PersonaItem;
    }else if (response.responseCode === 400) {
      // 后端返回了具体的错误信息
      const errResult:Record<string, Object> = JSON.parse(response.result as string);
      throw new Error(errResult['detail'] as string)|| '创建失败';
    }
    return null;
  } finally {
    httpRequest.destroy();
  }
}

export async function updatePersona(personaId: number, name?: string, corePrinciple?: string, weight?: number,riskPreference?: string): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const body: Record<string, Object> = {};
    if (name !== undefined) body['name'] = name;
    if (corePrinciple !== undefined) body['core_principle'] = corePrinciple;
    if (weight !== undefined) body['weight'] = weight;
    if (riskPreference !== undefined) body['risk_preference'] = riskPreference;
    const response = await httpRequest.request(baseUrl + '/api/personas/' + personaId + '/update', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: JSON.stringify(body),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}

export async function deletePersona(personaId: number): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/personas/' + personaId, {
      method: http.RequestMethod.DELETE,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally {
    httpRequest.destroy();
  }
}

export async function resetPersona(personaId: number): Promise<PersonaItem | null> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/personas/' + personaId + '/reset', {
      method: http.RequestMethod.POST,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000,
      readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as PersonaItem;
    }
    return null;
  } finally {
    httpRequest.destroy();
  }
}


export async function getConversationPersonas(convId: number): Promise<number[]> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId + '/personas', {
      method: http.RequestMethod.GET,
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000, readTimeout: 10000
    });
    if (response.responseCode === 200) {
      return JSON.parse(response.result as string) as number[];
    }
    return [];
  } finally { httpRequest.destroy(); }
}

export async function saveConversationPersonas(convId: number, personaIds: number[]): Promise<boolean> {
  const baseUrl = await Constants.getBaseUrl();
  const httpRequest = http.createHttp();
  try {
    const response = await httpRequest.request(baseUrl + '/api/conversations/' + convId + '/personas', {
      method: http.RequestMethod.POST,
      header: { 'Content-Type': 'application/json' },
      extraData: JSON.stringify({ persona_ids: personaIds }),
      expectDataType: http.HttpDataType.STRING,
      connectTimeout: 5000, readTimeout: 10000
    });
    return response.responseCode === 200;
  } finally { httpRequest.destroy(); }
}