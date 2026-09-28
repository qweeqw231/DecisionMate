//src/main/ets/pages/InputPage.ets
import router from '@ohos.router';
import { ConversationItem, MessageItem, DecisionReport } from '../models/DecisionModels';
import {
  createConversation, getConversations, getMessages, sendMessage,
  renameConversation, deleteConversation,
  togglePinConversation
} from '../services/DecisionService';
import { ArchiveReport,PersonaItem } from '../models/DecisionModels';
import { submitFeedback,addUserFactor,getConversationPersonas,saveConversationPersonas,getPersonas } from '../services/DecisionService'
import pasteboard from '@ohos.pasteboard';

class NormalizedPersona {
  persona_id: number = 0;
  normalized_weight: number = 0;
}

@Entry
@Component
struct InputPage {
  @State conversations: ConversationItem[] = [];
  @State currentConvId: number = -1;
  @State messages: MessageItem[] = [];
  @State inputText: string = '';
  @State isLoading: boolean = false;
  @State showSidebar: boolean = false;
  @State renameText: string = '';
  @State renameTargetId: number = -1;
  @State isRenameDialogVisible: boolean = false;
  // Phase 3.3 新增状态
  @State showFeedbackDialog: boolean = false;
  @State feedbackTargetConvId: number = -1;
  @State feedbackTargetMsgId: number = -1;
  @State feedbackType: string = '';
  @State feedbackText: string = '';
  @State archiveReports: Map<number, ArchiveReport> = new Map(); // key: messageId
  @State isSubmitting: boolean = false;
  @State activatedPersonaIds: number[] = [];           // 当前激活的分身ID列表
  @State allPersonas: PersonaItem[] = [];              // 所有可用分身
  @State showPersonaSelector: boolean = false;          // 是否显示分身选择弹窗


  async aboutToAppear() {
    await this.refreshConversations();
    await this.loadAllPersonas();

    if (this.conversations.length === 0) {
      // 没有任何对话，创建一个新的
      await this.createNewConversation();
    } else {
      // 检查当前对话是否还存在
      const exists = this.conversations.find(c => c.id === this.currentConvId);
      if (!exists) {
        // 之前的对话已被清空，切换到第一个
        this.currentConvId = this.conversations[0].id;
      }
      this.activatedPersonaIds = [];  // ← 强制清空
      // 无论当前对话是新是旧，加载其分身和消息
      await this.loadActivatedPersonas();
      await this.loadMessages();
    }
  }

  async refreshConversations() {
    this.conversations = await getConversations();
  }

  async loadMessages() {
    if (this.currentConvId > 0) {
      try {
        this.messages = await getMessages(this.currentConvId);
      } catch (err) {
        console.error('loadMessages error: ' + JSON.stringify(err));
      }
    }
  }

  async createNewConversation() {
    const conv = await createConversation();
    if (conv && conv.id) {
      this.currentConvId = conv.id;
      this.messages = [];
      await this.refreshConversations();

      // 默认激活中性分身（使用 conv.id，确保保存到正确的对话）
      const neutralPersona = this.allPersonas.find(p => p.risk_preference === 'neutral');
      if (neutralPersona) {
        this.activatedPersonaIds = [neutralPersona.id];
        await saveConversationPersonas(conv.id, this.activatedPersonaIds);  // ← 用 conv.id
      }
      this.showSidebar = false;
    }
  }

  async selectConversation(convId: number) {
    this.currentConvId = convId;
    this.showSidebar = false;
    this.activatedPersonaIds = [];  // 清空旧状态
    await this.loadMessages();
    await this.loadActivatedPersonas();  // 加载该对话的分身
  }

  async handleSend() {
    const text = this.inputText.trim();
    if (!text || this.isLoading) return;

    this.inputText = '';
    this.isLoading = true;

    try {
      // 计算归一化权重
      const activatedPersonas = this.getActivatedPersonas();
      const totalWeight = activatedPersonas.reduce((sum, p) => sum + p.weight, 0) || 1.0;
      const normalizedPersonas:NormalizedPersona[] = activatedPersonas.map(p => {
        const np = new NormalizedPersona();
        np.persona_id=p.id;
        np.normalized_weight=p.weight / totalWeight;
        return np;
      });

      await sendMessage(this.currentConvId, text,normalizedPersonas);
      await this.loadMessages();
    } catch (err) {
      console.error('Send failed: ' + JSON.stringify(err));
    } finally {
      this.isLoading = false;
    }
  }

  confirmRename = async () => {
    const newTitle = this.renameText.trim();
    if (newTitle) {
      // 1. 调用后端 API 更新数据库
      await renameConversation(this.renameTargetId, newTitle);

      // 2. 乐观更新本地列表（立即生效，无需重新拉取）
      const updated = this.conversations.map(conv => {
        if (conv.id === this.renameTargetId) {
          // 手动创建新对象，逐字段复制
          const newConv = new ConversationItem();
          newConv.id = conv.id;
          newConv.title = newTitle;
          newConv.created_at = conv.created_at;
          newConv.updated_at = conv.updated_at;
          newConv.message_count = conv.message_count;
          newConv.is_pinned = conv.is_pinned;
          return newConv;
        }
        return conv;
      });
      this.conversations = updated;  // 替换数组引用，触发 @State 更新

      // 3. 关闭对话框并清空输入
      this.isRenameDialogVisible = false;
      this.renameText = '';
    }
  }

  showConversationMenu(convId: number, convTitle: string) {
    AlertDialog.show({
      title: '操作对话',
      message: '选择对“' + convTitle + '”的操作',
      autoCancel: true,
      alignment: DialogAlignment.Center,
      primaryButton: {
        value: '重命名',
        action: () => {
          this.openRenameDialog(convId, convTitle);
        }
      },
      secondaryButton: {
        value: '删除',
        fontColor: '#e74c3c',
        action: () => {
          this.confirmDeleteConversation(convId);
        }
      }
    });
  }

  openRenameDialog(convId: number, oldTitle: string) {
    this.renameTargetId = convId;
    this.renameText = oldTitle;
    this.isRenameDialogVisible = true;
  }

  confirmDeleteConversation(convId: number) {
    AlertDialog.show({
      title: '确认删除',
      message: '确认删除此对话？删除后内容无法恢复。',
      autoCancel: true,
      alignment: DialogAlignment.Center,
      primaryButton: {
        value: '取消',
        action: () => { }
      },
      secondaryButton: {
        value: '确认删除',
        fontColor: '#e74c3c',
        action: async () => {
          await deleteConversation(convId);
          await this.refreshConversations();
          if (this.currentConvId === convId) {
            if (this.conversations.length > 0) {
              this.currentConvId = this.conversations[0].id;
              await this.loadMessages();
            } else {
              await this.createNewConversation();
            }
          }
        }
      }
    });
  }

  openFeedbackDialog(convId: number, msgId: number) {
    this.feedbackTargetConvId = convId;
    this.feedbackTargetMsgId = msgId;
    this.feedbackType = '';
    this.feedbackText = '';
    this.showFeedbackDialog = true;
  }

  async submitFeedback() {
    console.log('submitFeedback called, feedbackType=' + this.feedbackType);
    if (!this.feedbackType) return;
    if (this.isSubmitting) return; // 防止重复提交

    this.isSubmitting = true;
    try {
      console.log('calling submitFeedback API...');
      const report = await submitFeedback(
        this.feedbackTargetConvId,
        this.feedbackTargetMsgId,
        this.feedbackType,
        this.feedbackText
      );
      console.log('submitFeedback API success');
      // 存储复盘报告
      this.archiveReports.set(this.feedbackTargetMsgId, report);
      // 关闭对话框
      this.showFeedbackDialog = false;
      // 可以显示一个短暂的成功提示
      console.info('Feedback submitted successfully');
    } catch (err) {
      console.error('Submit feedback error: ' + JSON.stringify(err));
      // 弹出错误信息方便调试
      AlertDialog.show({
        title: '提交失败',
        message: JSON.stringify(err),
        autoCancel: true,
        primaryButton: { value: '确定', action: () => {} }
      });
    } finally {
      this.isSubmitting = false;
    }
  }

  acceptNewFactor(msgId:number,factorName: string, value: number, basis: string) {
    // 调用后端 API 添加新因子（当前后端接口已就绪，直接调用）
    try {
      // 乐观更新：立即给用户反馈，同时异步调用后端
      console.log('New factor accepted: ' + factorName);

      // 乐观更新：立即更新本地状态
      const archive = this.archiveReports.get(msgId);
      if (archive && archive.new_factor_proposal) {
        archive.new_factor_proposal.status = 'accepted';
        // 强制触发 UI 刷新
        this.archiveReports = new Map(this.archiveReports);
      }

      AlertDialog.show({
        title: '已添加',
        message: `新因子“${factorName}”已添加（初始值：${value}）`,
        autoCancel: true,
        primaryButton: { value: '确定', action: () => {} }
      });
      // 异步调用后端，失败也仅打印日志，不影响前端状态，忽略 Promise 错误
      addUserFactor(factorName, value, basis).catch((err: Error) => {
        console.error('addUserFactor failed: ' + JSON.stringify(err));
      });
    } catch (err) {
      console.error('acceptNewFactor error: ' + JSON.stringify(err));
      AlertDialog.show({
        title: '添加失败',
        message: '请稍后重试',
        autoCancel: true,
        primaryButton: { value: '确定', action: () => {} }
      });
    }
  }

  /**
   * 拼接复盘报告为纯文本
   */
  formatArchiveReport(msgId: number): string {
    const archive = this.archiveReports.get(msgId);
    if (!archive) return '';

    const separator = '━━━━━━━━━━━━━━━━━━━━━━━━━━';
    let text = '【复盘分析报告】\n';
    text += `${separator}\n\n`;

    text += `📊 初始预判\n`;
    text += `  • 最优下注比例 f*：${archive.initial_f_star.toFixed(4)}\n`;
    text += `  • 反馈类型：${archive.feedback_type}\n\n`;

    text += `${separator}\n\n`;

    text += `🔍 偏差分析\n`;
    text += `${archive.deviation_analysis}\n\n`;

    // 能力因子更新
    const updates = archive.factor_updates;
    if (updates && Object.keys(updates).length > 0) {
      text += `${separator}\n\n`;
      text += `📈 能力因子更新\n`;
      const keys = Object.keys(updates);
      for (let i = 0; i < keys.length; i++) {
        const factor = keys[i];
        const update = updates[factor];
        if (update && update.old !== undefined && update.new !== undefined) {
          text += `  • ${factor}：${update.old} → ${update.new}\n`;
        }
      }
    }

    // 可复用模式
    if (archive.reusable_pattern) {
      text += `\n${separator}\n\n`;
      text += `💡 可复用模式\n`;
      text += `${archive.reusable_pattern}\n`;
    }

    // 新因子提议
    if (archive.new_factor_proposal) {
      const nfp = archive.new_factor_proposal;
      text += `\n${separator}\n\n`;
      text += `🆕 新因子提议\n`;
      text += `  • 因子名称：${nfp.factor_name}\n`;
      text += `  • 建议初始值：${nfp.suggested_value.toFixed(2)}\n`;
      text += `  • 依据：${nfp.basis}\n`;
      if (nfp.data_insufficient) {
        text += `  • 注意：数据尚不充分，建议积累更多数据后确认\n`;
      }
    }

    text += `\n${separator}\n`;
    text += `—— 基于多Agent的个人决策支持系统 · DecisionMate`;

    return text;
  }

  /**
   * 复制文本到系统剪贴板
   */
  copyToClipboard(text: string) {
    try {
      const pasteData = pasteboard.createData(pasteboard.MIMETYPE_TEXT_PLAIN, text);
      pasteboard.getSystemPasteboard().setData(pasteData, (err) => {
        if (err) {
          console.error('复制失败: ' + JSON.stringify(err));
        }
      });
    } catch (error) {
      console.error('copyToClipboard error: ' + JSON.stringify(error));
    }
  }

  async loadActivatedPersonas() {
    if (this.currentConvId > 0) {
      console.log('=== loadActivatedPersonas ===');
      console.log('currentConvId:', this.currentConvId);
      this.activatedPersonaIds = await getConversationPersonas(this.currentConvId);
      console.log('loaded personaIds:', JSON.stringify(this.activatedPersonaIds));
      // 如果没有任何激活分身，默认激活中性分身
      if (this.activatedPersonaIds.length === 0) {
        console.log('!!! 触发了默认中性分身保存，convId=' + this.currentConvId);
        const neutralPersona = this.allPersonas.find(p => p.risk_preference === 'neutral');
        if (neutralPersona) {
          this.activatedPersonaIds = [neutralPersona.id];
          await saveConversationPersonas(this.currentConvId, this.activatedPersonaIds);
          console.log('defaulted to neutral persona, saved');
        }
      }
    }
  }

  getActivatedPersonas(): PersonaItem[] {
    return this.allPersonas.filter(p => this.activatedPersonaIds.includes(p.id));
  }

  removeActivatedPersona(personaId: number) {
    this.activatedPersonaIds = this.activatedPersonaIds.filter(id => id !== personaId);
    saveConversationPersonas(this.currentConvId, this.activatedPersonaIds);
  }

  togglePersonaInSelector(personaId: number) {
    if (this.activatedPersonaIds.includes(personaId)) {
      this.activatedPersonaIds = this.activatedPersonaIds.filter(id => id !== personaId);
    } else {
      this.activatedPersonaIds = [...this.activatedPersonaIds, personaId];
    }
  }

  confirmPersonaSelection() {
    console.log('=== confirmPersonaSelection ===');
    console.log('currentConvId:', this.currentConvId);
    console.log('activatedPersonaIds:', JSON.stringify(this.activatedPersonaIds));
    saveConversationPersonas(this.currentConvId, this.activatedPersonaIds);
    this.showPersonaSelector = false;
  }

  async handleSelectConversation(convId: number) {
    this.currentConvId = convId;
    this.showSidebar = false;
    this.activatedPersonaIds = [];  // ← 强制清空，避免闪现旧数据
    await this.loadMessages();
    await this.loadActivatedPersonas();  // ← 必须有这一行
  }

  async loadAllPersonas() {
    this.allPersonas = await getPersonas();
  }

  @Builder
  ArchiveCard(msgId: number) {
    if (this.archiveReports.has(msgId)) {
      Column() {
        Row() {
          // 标题行：复盘摘要 + 复制按钮
          Text('📊 复盘摘要')
            .fontSize(13)
            .fontWeight(FontWeight.Bold)
            .fontColor('#2c3e50')
            .margin({ bottom: 4 })

          Button() {
            Text('📋 复制')
              .fontSize(11)
              .fontColor('#3498db')
          }
          .backgroundColor(Color.Transparent)
          .borderRadius(4)
          .padding({
            left: 8,
            right: 8,
            top: 4,
            bottom: 4
          })
          .onClick(() => {
            const text = this.formatArchiveReport(msgId);
            if (text) {
              this.copyToClipboard(text);
            }
          })
        }
        .width('100%')
        .margin({ bottom: 8 })

        Text('初始预判：f* = ' + this.archiveReports.get(msgId)!.initial_f_star.toFixed(4) +
          '，实际结果：' + this.archiveReports.get(msgId)!.feedback_type)
          .fontSize(11)
          .fontColor('#555')

        Text(this.archiveReports.get(msgId)!.deviation_analysis)
          .fontSize(11)
          .fontColor('#555')
          .maxLines(2)

        // 能力因子更新
        if (Object.keys(this.archiveReports.get(msgId)!.factor_updates).length > 0) {
          Text('能力因子更新：')
            .fontSize(11)
            .fontWeight(FontWeight.Medium)
            .fontColor('#2c3e50')
          ForEach(Object.keys(this.archiveReports.get(msgId)!.factor_updates), (factor: string) => {
            Text(factor + ': ' +
            this.archiveReports.get(msgId)!.factor_updates[factor].old + ' → ' +
            this.archiveReports.get(msgId)!.factor_updates[factor].new)
              .fontSize(10)
              .fontColor('#555')
          })
        }

        // 新因子提议
        if (this.archiveReports.get(msgId)!.new_factor_proposal) {

          Column() {
            Text('💡 新因子提议：' + this.archiveReports.get(msgId)!.new_factor_proposal!.factor_name)
              .fontSize(11)
              .fontWeight(FontWeight.Medium)
            Text('建议初始值：' + this.archiveReports.get(msgId)!.new_factor_proposal!.suggested_value.toFixed(2))
              .fontSize(10)
            Text('依据：' + this.archiveReports.get(msgId)!.new_factor_proposal!.basis)
              .fontSize(10)
            Row() {
              if (this.archiveReports.get(msgId)!.new_factor_proposal!.status === 'pending') {
                Button('接受提议')
                  .fontSize(10)
                  .backgroundColor('#27ae60')
                  .fontColor('#fff')
                  .borderRadius(4)
                  .onClick(() => {
                    this.acceptNewFactor(msgId,
                      this.archiveReports.get(msgId)!.new_factor_proposal!.factor_name,
                      this.archiveReports.get(msgId)!.new_factor_proposal!.suggested_value,
                      this.archiveReports.get(msgId)!.new_factor_proposal!.basis);
                    this.archiveReports.get(msgId)!.new_factor_proposal!.basis
                  })
                Button('忽略')
                  .fontSize(10)
                  .backgroundColor('#bdc3c7')
                  .fontColor('#fff')
                  .borderRadius(4)
                  .margin({ left: 8 })
                  .onClick(() => {
                    const archive = this.archiveReports.get(msgId);
                    if (archive && archive.new_factor_proposal) {
                      archive.new_factor_proposal.status = 'ignored';
                      this.archiveReports = new Map(this.archiveReports);
                    }
                  })
              } else if (this.archiveReports.get(msgId)!.new_factor_proposal!.status === 'accepted') {
                // 已接受状态
                Text('✅ 已接受，新因子已添加')
                  .fontSize(10)
                  .fontColor('#27ae60')
              } else if (this.archiveReports.get(msgId)!.new_factor_proposal!.status === 'ignored') {
                // 已忽略状态
                Text('⏭️ 已忽略')
                  .fontSize(10)
                  .fontColor('#95a5a6')
              }
            }
          }
          .backgroundColor('#f9f9f9')
          .borderRadius(8)
          .padding(8)
          .margin({ top: 8 })
        }
      }
      .backgroundColor('#eaf7e8')
      .borderRadius(8)
      .padding(12)
      .margin({ top: 8 })
      .width('100%')
    }
  }

  build() {
    Stack() {
      // ==========================================
      // 主聊天区域（固定在底层）
      // ==========================================
      Column() {
        // 固定标题栏
        Row() {
          Button() {
            Text('≡')
              .fontSize(22)
              .fontColor('#333333')
          }
          .backgroundColor(Color.Transparent)
          .onClick(() => {
            this.showSidebar = !this.showSidebar;
          })

          Text(this.conversations.find(c => c.id === this.currentConvId)?.title || '决策Mate')
            .fontSize(18)
            .fontWeight(FontWeight.Bold)
            .layoutWeight(1)
            .textAlign(TextAlign.Center)

          Button() {
            Text('⚙️')
              .fontSize(20)
          }
          .backgroundColor(Color.Transparent)
          .onClick(() => {
            router.pushUrl({ url: 'pages/SettingsPage' });
          })
        }
        .width('100%')
        .padding({ left: 16, right: 16, top: 12, bottom: 8 })
        .backgroundColor('#ffffff')

        Divider().color('#e0e0e0')

        // 消息列表（可滚动）
        Scroll() {
          Column() {
            ForEach(this.messages, (msg: MessageItem) => {
              if (msg.role === 'user') {
                Row() {
                  Blank()
                  Text(msg.content)
                    .fontSize(14)
                    .fontColor('#333333')
                    .backgroundColor('#eaf2f8')
                    .borderRadius(12)
                    .padding(12)
                    .constraintSize({ maxWidth: '70%' })
                }
                .width('100%')
                .padding({ left: 16, right: 16, top: 6, bottom: 6 })
                .justifyContent(FlexAlign.End)
              } else {
                Column() {
                  Text(this.getSummary(msg.content))
                    .fontSize(14)
                    .fontColor('#555555')
                    .backgroundColor('#ffffff')
                    .borderRadius(12)
                    .padding(12)
                    .constraintSize({ maxWidth: '85%' })
                    .maxLines(3)
                    .shadow({ radius: 2, color: '#00000010', offsetX: 0, offsetY: 1 })

                  Text('点击查看完整报告 →')
                    .fontSize(11)
                    .fontColor('#3498db')
                    .margin({ top: 4, left: 4 })

                  // Phase 3.3: 反馈入口
                  if (!this.archiveReports.has(msg.id)) {
                    Text('💬 记录实际结果 →')
                      .fontSize(11)
                      .fontColor('#27ae60')
                      .margin({ top: 4, left: 4 })
                      .onClick(() => {
                        this.openFeedbackDialog(this.currentConvId, msg.id);
                      })
                  }

                  // Phase 3.3: 复盘摘要卡片
                  this.ArchiveCard(msg.id)
                }
                .width('100%')
                .padding({ left: 16, right: 16, top: 6, bottom: 6 })
                .alignItems(HorizontalAlign.Start)
                .onClick(() => {
                  try {
                    const report: DecisionReport = JSON.parse(msg.content) as DecisionReport;
                    router.pushUrl({
                      url: 'pages/ResultPage',
                      params: { report: report,
                        convId: this.currentConvId,  // 新增
                        msgId: msg.id                 // 新增
                      }
                    });
                  } catch (e) {
                    console.error('Parse error: ' + JSON.stringify(e));
                  }
                })
              }
            })
            Row().height(16)
          }
          .width('100%')
        }
        .layoutWeight(1)
        .scrollable(ScrollDirection.Vertical)

        // 分身选择器（输入框上方）
        Row() {
          Scroll() {
            Row() {
              ForEach(this.getActivatedPersonas(), (persona: PersonaItem) => {
                Row() {
                  Text(persona.name)
                    .fontSize(12).fontColor('#ffffff')
                  Button() {
                    Text('✕').fontSize(10).fontColor('#ffffff')
                  }
                  .backgroundColor(Color.Transparent).width(20).height(20)
                  .onClick(() => this.removeActivatedPersona(persona.id))
                }
                .backgroundColor('#3498db').borderRadius(12)
                .padding({ left: 10, right: 10, top: 4, bottom: 4 })
                .margin({ right: 6 })
              })

              // “+ 分身”按钮
              Button() {
                Text('+ 分身').fontSize(12).fontColor('#3498db')
              }
              .backgroundColor(Color.Transparent).borderRadius(12)
              .padding({ left: 10, right: 10, top: 4, bottom: 4 })
              .border({ width: 1, color: '#3498db' })
              .onClick(() => {
                this.loadAllPersonas();  // ← 新增：每次打开弹窗前重新拉取
                this.showPersonaSelector = true; })
            }
          }
          .scrollable(ScrollDirection.Horizontal)
        }
        .width('100%').padding({ left: 12, right: 12, top: 4, bottom: 4 })

        // 底部输入区域
        Row() {
          TextInput({ text: this.inputText, placeholder: '描述你的决策困境...' })
            .layoutWeight(1)
            .height(44)
            .fontSize(14)
            .backgroundColor('#f8f9fa')
            .borderRadius(22)
            .padding({ left: 16, right: 16 })
            .onChange((value: string) => {
              this.inputText = value;
            })
            .onSubmit(() => {
              this.handleSend();
            })

          Button() {
            Text(this.isLoading ? '分析中...' : '决策')
              .fontSize(14)
              .fontColor('#ffffff')
          }
          .height(40)
          .padding({ left: 16, right: 16 })
          .backgroundColor(this.isLoading || !this.inputText.trim() ? '#bdc3c7' : '#2980b9')
          .borderRadius(24)
          .margin({ left: 8 })
          .enabled(!this.isLoading && this.inputText.trim().length > 0)
          .onClick(() => this.handleSend())
        }
        .width('100%')
        .padding({ left: 12, right: 12, top: 8, bottom: 12 })
        .backgroundColor('#ffffff')


      // ==========================================
      // 侧边栏覆盖层（显示时浮在最上层）
      // ==========================================
      if (this.showSidebar) {
        Row() {
          // 左侧对话列表
          Column() {
            Row() {
              Text('对话列表')
                .fontSize(16)
                .fontWeight(FontWeight.Bold)
                .layoutWeight(1)

              Button() {
                Text('+')
                  .fontSize(20)
                  .fontColor('#27ae60')
              }
              .backgroundColor(Color.Transparent)
              .onClick(() => this.createNewConversation())
            }
            .width('100%')
            .padding({ left: 12, right: 12, top: 16, bottom: 8 })

            Divider().color('#e0e0e0')

            Scroll() {
              Column() {
                ForEach(this.conversations, (item: ConversationItem) => {
                  Row() {
                    Text(item.title)
                      .fontSize(14)
                      .fontColor(this.currentConvId === item.id ? '#2980b9' : '#333333')
                      .fontWeight(this.currentConvId === item.id ? FontWeight.Bold : FontWeight.Regular)
                      .maxLines(1)
                      .layoutWeight(1)

                    // 置顶图钉按钮（所有项都显示，颜色区分状态）
                    Button() {
                      Text(item.is_pinned ? '★' : '☆')
                        .fontSize(20)
                        .fontColor(item.is_pinned ? '#e74c3c' : '#bdc3c7') // 红色：已置顶，灰色：未置顶
                    }
                    .backgroundColor(Color.Transparent)
                    .width(32)
                    .height(32)
                    .onClick(async () => {
                      await togglePinConversation(item.id);
                      await this.refreshConversations();
                    })

                    Button() {
                      Text('⋯')
                        .fontSize(18)
                        .fontColor('#999999')
                    }
                    .backgroundColor(Color.Transparent)
                    .width(32)
                    .height(32)
                    .onClick(() => {
                      this.showConversationMenu(item.id, item.title);
                    })
                  }
                  .width('100%')
                  .padding({ left: 12, right: 8, top: 12, bottom: 4 })
                  .onClick(() => {
                    this.selectConversation(item.id);
                  })

                  Text(item.updated_at.substring(0, 10))
                    .fontSize(10)
                    .fontColor('#bdc3c7')
                    .width('100%')
                    .padding({ left: 12, right: 12, bottom: 8 })
                })
              }
            }
            .layoutWeight(1)
          }
          .width('50%')
          .height('100%')
          .backgroundColor('#ffffff')

          // 右侧遮罩
          Column()
            .width('50%')
            .height('100%')
            .backgroundColor('rgba(0,0,0,0.4)')
            .onClick(() => {
              this.showSidebar = false;
            })
        }
        .width('100%')
        .height('100%')
        .position({ x: 0, y: 0 })
      }
      // ==========================================
      // 自定义重命名对话框
      // ==========================================
      if (this.isRenameDialogVisible) {
        Column() {
          Column() {
            Text('重命名对话')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .margin({ bottom: 12 })

            TextInput({ text: this.renameText })
              .width('100%')
              .height(40)
              .fontSize(14)
              .backgroundColor('#f8f9fa')
              .borderRadius(8)
              .padding(8)
              .onChange((value: string) => {
                this.renameText = value;
              })

            Row() {
              Button('取消')
                .backgroundColor('#bdc3c7')
                .fontColor('#ffffff')
                .borderRadius(8)
                .padding({ left: 16, right: 16 })
                .onClick(() => {
                  this.isRenameDialogVisible = false;
                })

              Button('确认')
                .backgroundColor('#2980b9')
                .fontColor('#ffffff')
                .borderRadius(8)
                .padding({ left: 16, right: 16 })
                .onClick(() => this.confirmRename())
            }
            .width('100%')
            .justifyContent(FlexAlign.SpaceBetween)
            .margin({ top: 12 })
          }
          .width('80%')
          .backgroundColor('#ffffff')
          .borderRadius(12)
          .padding(20)
        }
        .width('100%')
        .height('100%')
        .backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center)
        .position({ x: 0, y: 0 })
        .onClick(() => {
          this.isRenameDialogVisible = false;
        })
      }
      // ==========================================
      //   Phase 3.3: 反馈对话框
      // ==========================================
      if (this.showFeedbackDialog) {
        Column() {
          Column() {
            Text('记录实际结果')
              .fontSize(16)
              .fontWeight(FontWeight.Bold)
              .margin({ bottom: 12 })

            Row() {
              Button('有用 ✓')
                .backgroundColor(this.feedbackType === 'useful' ? '#27ae60' : '#ecf0f1')
                .fontColor(this.feedbackType === 'useful' ? '#fff' : '#555')
                .borderRadius(8)
                .padding({ left: 12, right: 12 })
                .onClick(() => { this.feedbackType = 'useful'; })

              Button('不太准 ✗')
                .backgroundColor(this.feedbackType === 'inaccurate' ? '#e74c3c' : '#ecf0f1')
                .fontColor(this.feedbackType === 'inaccurate' ? '#fff' : '#555')
                .borderRadius(8)
                .padding({ left: 12, right: 12 })
                .margin({ left: 12 })
                .onClick(() => { this.feedbackType = 'inaccurate'; })
            }
            .margin({ bottom: 12 })

            TextInput({ text: this.feedbackText, placeholder: '补充说明（可选）' })
              .width('100%')
              .height(40)
              .fontSize(14)
              .backgroundColor('#f8f9fa')
              .borderRadius(8)
              .padding(8)
              .onChange((value: string) => { this.feedbackText = value; })

            Row() {
              Button('取消')
                .backgroundColor('#bdc3c7')
                .fontColor('#fff')
                .borderRadius(8)
                .padding({ left: 16, right: 16 })
                .onClick(() => { this.showFeedbackDialog = false; })

              Button(this.isSubmitting ? '提交中...' : '提交')
                .backgroundColor('#2980b9')
                .fontColor('#fff')
                .borderRadius(8)
                .padding({ left: 16, right: 16 })
                .margin({ left: 12 })
                .enabled(this.feedbackType !== ''&& !this.isSubmitting)
                .onClick(() => this.submitFeedback())
            }
            .width('100%')
            .justifyContent(FlexAlign.SpaceBetween)
            .margin({ top: 12 })

          }
          .width('80%')
          .backgroundColor('#ffffff')
          .borderRadius(12)
          .padding(20)
          .onClick(() => {}) // 阻止事件冒泡到遮罩层
        }
        .width('100%')
        .height('100%')
        .backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center)
        .position({ x: 0, y: 0 })
        // 遮罩层的点击关闭事件依然保留
        .onClick(() => { this.showFeedbackDialog = false; })
      }
      // ==========================================
      //   Phase 4.2.3: 分身选择弹窗
      // ==========================================
      if (this.showPersonaSelector) {
        Column() {
          Column() {
            Text('选择参与决策的分身')
              .fontSize(16).fontWeight(FontWeight.Bold).margin({ bottom: 12 })
            ForEach(this.allPersonas, (persona: PersonaItem) => {
              Row() {
                Text(persona.name).fontSize(14).layoutWeight(1)
                Toggle({ type: ToggleType.Checkbox, isOn: this.activatedPersonaIds.includes(persona.id) })
                  .onChange((isOn: boolean) => {
                    this.togglePersonaInSelector(persona.id);
                  })
              }
              .width('100%').padding({ top: 8, bottom: 8 })
            })
            Row() {
              Button('取消').onClick(() => { this.showPersonaSelector = false; })
              Button('确认').onClick(() => this.confirmPersonaSelection())
            }
            .width('100%').justifyContent(FlexAlign.SpaceBetween).margin({ top: 12 })
          }
          .width('80%').backgroundColor('#ffffff').borderRadius(12).padding(20)
        }
        .width('100%').height('100%').backgroundColor('rgba(0,0,0,0.4)')
        .justifyContent(FlexAlign.Center).position({ x: 0, y: 0 })
        .onClick(() => { this.showPersonaSelector = false; })
      }
    }
    .width('100%')
    .height('100%')
    .backgroundColor('#f5f6fa')
    }
    .width('100%')
    .height('100%')
  }

  getSummary(content: string): string {
    try {
      const report: DecisionReport = JSON.parse(content) as DecisionReport;
      const lines = report.recommendation.split('\n');
      for (let i = 0; i < lines.length; i++) {
        if (lines[i].trim()) {
          return lines[i].trim();
        }
      }
      return '分析报告已生成，点击查看详情';
    } catch (e) {
      return content.substring(0, 100);
    }
  }
}