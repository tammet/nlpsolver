# Hans benchmark selected tests used by the nlptest.py

[
  # A selection of Hans tests for all different template-entailment-etc patterns: 
  # the ones which fail since the parse is wrong or confidences unexpected, are commented out

  ['The president advised the doctor . The doctor advised the president ?', None], #temp1_non-entailment_ln_subject/object_swap_lexical_overlap
  ['The student saw the managers . The managers saw the student ?', None], #temp1_non-entailment_ln_subject/object_swap_lexical_overlap
  ['The professors supported the tourists in front of the secretary . The tourists supported the professors ?', None], #temp5_non-entailment_ln_preposition_lexical_overlap
  ['The senators supported the secretary in front of the doctor . The doctor supported the senators ?', None], #temp7_non-entailment_ln_preposition_lexical_overlap
  ['The judges admired the senator behind the professor . The senator admired the judges ?', None], #temp5_non-entailment_ln_preposition_lexical_overlap
  ['The professor supported the manager in front of the banker . The banker supported the professor ?', None], #temp7_non-entailment_ln_preposition_lexical_overlap
  ['The judge in front of the manager saw the doctors . The doctors saw the judge ?', None], #temp3_non-entailment_ln_preposition_lexical_overlap
  ['The president next to the professor stopped the doctor . The professor stopped the president ?', None], #temp2_non-entailment_ln_preposition_lexical_overlap
  ['The judges by the tourists called the artists . The artists called the judges ?', None], #temp3_non-entailment_ln_preposition_lexical_overlap
  ['The students by the judge helped the president . The judge helped the students ?', None], #temp2_non-entailment_ln_preposition_lexical_overlap
  ['The secretaries next to the lawyer advised the scientist . The scientist advised the lawyer ?', None], #temp4_non-entailment_ln_preposition_lexical_overlap
  ['The judges helped the athletes near the president . The athletes helped the president ?', None], #temp6_non-entailment_ln_preposition_lexical_overlap
  ['The judge by the manager contacted the senator . The senator contacted the manager ?', None], #temp4_non-entailment_ln_preposition_lexical_overlap
  ['The senator avoided the bankers by the scientist . The bankers avoided the scientist ?', None], #temp6_non-entailment_ln_preposition_lexical_overlap
  ['The actors who advised the manager saw the tourists . The manager saw the actors ?', None], #temp11_non-entailment_ln_relative_clause_lexical_overlap
  ['The student who the senators thanked stopped the scientist . The scientist stopped the student ?', None], #temp9_non-entailment_ln_relative_clause_lexical_overlap
  ['The judges admired the lawyers that supported the secretaries . The lawyers admired the the secretaries ?', None], #temp15_non-entailment_ln_relative_clause_lexical_overlap
  ['The authors contacted the tourist that saw the professor . The professor contacted the authors ?', None], #temp16_non-entailment_ln_relative_clause_lexical_overlap
  ['The tourists who the lawyer helped encouraged the judges . The judges encouraged the lawyer ?', None], #temp10_non-entailment_ln_relative_clause_lexical_overlap
  ['The actors helped the senators who thanked the professors . The senators helped the the professors ?', None], #temp15_non-entailment_ln_relative_clause_lexical_overlap
  ['The manager who the tourists advised introduced the judge . The tourists introduced the manager ?', None], #temp8_non-entailment_ln_relative_clause_lexical_overlap
  ['The lawyer saw the senators that recommended the tourists . The tourists saw the lawyer ?', None], #temp16_non-entailment_ln_relative_clause_lexical_overlap
  ['The bankers admired the lawyer that the students supported . The lawyer admired the students ?', None], #temp18_non-entailment_ln_relative_clause_lexical_overlap
  ['The lawyers that contacted the tourists recognized the actors . The tourists recognized the lawyers ?', None], #temp11_non-entailment_ln_relative_clause_lexical_overlap
  ['The judges who admired the student helped the authors . The authors helped the judges ?', None], #temp12_non-entailment_ln_relative_clause_lexical_overlap
  ['The author thanked the secretary that encouraged the athlete . The secretary thanked the author ?', None], #temp14_non-entailment_ln_relative_clause_lexical_overlap
  ['The scientists believed the athlete that the actor introduced . The athlete believed the actor ?', None], #temp18_non-entailment_ln_relative_clause_lexical_overlap
  ['The author believed the lawyers that the managers introduced . The managers believed the author ?', None], #temp19_non-entailment_ln_relative_clause_lexical_overlap
  ['The secretaries helped the managers who the lawyers recommended . The lawyers helped the secretaries ?', None], #temp19_non-entailment_ln_relative_clause_lexical_overlap
  ['The judges who contacted the secretary encouraged the athlete . The athlete encouraged the secretary ?', None], #temp13_non-entailment_ln_relative_clause_lexical_overlap
  ['The artists that contacted the actor saw the scientist . The scientist saw the actor ?', None], #temp13_non-entailment_ln_relative_clause_lexical_overlap
  ['The professor that helped the students contacted the athletes . The athletes contacted the professor ?', None], #temp12_non-entailment_ln_relative_clause_lexical_overlap
  ['The senator admired the artists who helped the manager . The artists admired the senator ?', None], #temp14_non-entailment_ln_relative_clause_lexical_overlap
  ['The lawyers advised the professors that the student encouraged . The professors advised the lawyers ?', None], #temp17_non-entailment_ln_relative_clause_lexical_overlap
  ['The banker who the artist recommended encouraged the athlete . The artist encouraged the banker ?', None], #temp8_non-entailment_ln_relative_clause_lexical_overlap
  ['The judges who the tourist stopped thanked the banker . The banker thanked the judges ?', None], #temp9_non-entailment_ln_relative_clause_lexical_overlap
  ['The athlete who the banker called advised the scientist . The scientist advised the banker ?', None], #temp10_non-entailment_ln_relative_clause_lexical_overlap
  ['The manager thanked the tourist that the doctors stopped . The tourist thanked the manager ?', None], #temp17_non-entailment_ln_relative_clause_lexical_overlap
  ['The managers were advised by the athlete . The managers advised the athlete ?', None], #temp21_non-entailment_ln_passive_lexical_overlap
  ['The lawyers were recommended by the doctor . The lawyers recommended the doctor ?', None], #temp21_non-entailment_ln_passive_lexical_overlap
  ['The professor was helped by the doctors . The professor helped the doctors ?', None], #temp20_non-entailment_ln_passive_lexical_overlap
  ['The scientist was recommended by the doctor . The scientist recommended the doctor ?', None], #temp20_non-entailment_ln_passive_lexical_overlap
  ['The secretary and the managers saw the actor . The secretary saw the managers ?', None], #temp22_non-entailment_ln_conjunction_lexical_overlap
  ['The doctors advised the presidents and the tourists . The tourists advised the presidents ?', None], #temp25_non-entailment_ln_conjunction_lexical_overlap
  ['The authors recognized the president and the judges . The judges recognized the president ?', None], #temp25_non-entailment_ln_conjunction_lexical_overlap
  ['The students and the lawyer recommended the secretary . The students recommended the lawyer ?', None], #temp22_non-entailment_ln_conjunction_lexical_overlap
  ['The athlete believed the judges and the artist . The judges believed the artist ?', None], #temp24_non-entailment_ln_conjunction_lexical_overlap
  ['The scientist supported the bankers and the doctor . The bankers supported the doctor ?', None], #temp24_non-entailment_ln_conjunction_lexical_overlap
  ['The professor and the senator encouraged the scientist . The senator encouraged the professor ?', None], #temp23_non-entailment_ln_conjunction_lexical_overlap
  ['The president and the artists believed the secretary . The artists believed the president ?', None], #temp23_non-entailment_ln_conjunction_lexical_overlap
  ['The judges recommended the tourist that believed the authors . The tourist believed the authors ?', True], #temp28_entailment_le_relative_clause_lexical_overlap
  ['The tourist advised the artists who admired the secretaries . The artists admired the secretaries ?', True], #temp28_entailment_le_relative_clause_lexical_overlap
  ['The actors that the students contacted admired the lawyer . The students contacted the actors ?', True], #temp26_entailment_le_relative_clause_lexical_overlap
  ['The judge admired the professor who the authors avoided . The authors avoided the professor ?', True], #temp29_entailment_le_relative_clause_lexical_overlap
  ['The secretary advised the managers who the actors introduced . The actors introduced the managers ?', True], #temp29_entailment_le_relative_clause_lexical_overlap
  ['The banker who the athletes recognized thanked the authors . The athletes recognized the banker ?', True], #temp26_entailment_le_relative_clause_lexical_overlap
  ['The actors who avoided the senators encouraged the professor . The actors avoided the senators ?', True], #temp27_entailment_le_relative_clause_lexical_overlap
  ['The secretaries who thanked the artist called the tourists . The secretaries thanked the artist ?', True], #temp27_entailment_le_relative_clause_lexical_overlap
  ['The bankers near the secretary called the doctor . The bankers called the doctor ?', True], #temp30_entailment_le_around_prepositional_phrase_lexical_overlap
  ['The president in front of the professor advised the authors . The president advised the authors ?', True], #temp30_entailment_le_around_prepositional_phrase_lexical_overlap
  ['The professors who introduced the lawyers admired the managers . The professors admired the managers ?', True], #temp31_entailment_le_around_relative_clause_lexical_overlap
  ['The actors that danced saw the author . The actors saw the author ?', True], #temp31_entailment_le_around_relative_clause_lexical_overlap
  ['The tourists and the senators admired the athletes . The tourists admired the athletes ?', True], #temp32_entailment_le_conjunction_lexical_overlap
  ['The professors and the lawyers recommended the student . The professors recommended the student ?', True], #temp32_entailment_le_conjunction_lexical_overlap
  ['The secretaries encouraged the scientists and the actors . The secretaries encouraged the actors ?', True], #temp33_entailment_le_conjunction_lexical_overlap
  ['The managers encouraged the senator and the lawyer . The managers encouraged the lawyer ?', True], #temp33_entailment_le_conjunction_lexical_overlap
  ['The authors were supported by the tourist . The tourist supported the authors ?', True], #temp36_entailment_le_passive_lexical_overlap
  ['The tourists were contacted by the athlete . The athlete contacted the tourists ?', True], #temp36_entailment_le_passive_lexical_overlap
  ['The actor was encouraged by the president . The president encouraged the actor ?', True], #temp35_entailment_le_passive_lexical_overlap
  ['The artist was mentioned by the professor . The professor mentioned the artist ?', True], #temp35_entailment_le_passive_lexical_overlap
  ['The manager knew the tourists supported the author . The manager knew the tourists ?', None], #temp37_non-entailment_sn_NP/S_subsequence
  ['The manager knew the athlete mentioned the actor . The manager knew the athlete ?', None], #temp37_non-entailment_sn_NP/S_subsequence
  ['The managers next to the professors performed . The professors performed ?', None], #temp38_non-entailment_sn_PP_on_subject_subsequence
  ['The actors behind the doctors supported the authors . The doctors supported the authors ?', None], #temp38_non-entailment_sn_PP_on_subject_subsequence
  ['The artists that supported the senators shouted . The senators shouted ?', None], #temp39_non-entailment_sn_relative_clause_on_subject_subsequence
  ['The presidents who stopped the scientist ran . The scientist ran ?', None], #temp39_non-entailment_sn_relative_clause_on_subject_subsequence
  ['The scientist presented in the school stopped the artists . The scientist presented in the school ?', None], #temp40_non-entailment_sn_past_participle_subsequence
  ['The athletes presented in the library mentioned the secretary . The athletes presented in the library ?', None], #temp40_non-entailment_sn_past_participle_subsequence
  ['The scientist contacted the manager investigated in the office . The manager investigated in the office ?', None], # ok with stanza 1.5, #temp41_non-entailment_sn_past_participle_subsequence
  ['The actor helped the managers presented in the laboratory . The managers presented in the laboratory ?', None], #temp41_non-entailment_sn_past_participle_subsequence
  #['Since the athlete hid the secretaries introduced the president . The athlete hid the secretaries ?', None], #temp42_non-entailment_sn_NP/Z_subsequence
  #['Before the actors presented the professors advised the manager . The actors presented the professors ?', None], #temp42_non-entailment_sn_NP/Z_subsequence
  ['When the students fought the secretary ran . The students fought the secretary ?', None], #temp43_non-entailment_sn_NP/Z_subsequence
  #['While the doctors fought the manager encouraged the athletes . The doctors fought the manager ?', None], #temp43_non-entailment_sn_NP/Z_subsequence
  ['The tourist and the scientists admired the doctors . The scientists admired the doctors ?', True], #temp44_entailment_se_conjunction_subsequence
  ['The professor and the banker saw the author . The banker saw the author ?', True], #temp44_entailment_se_conjunction_subsequence
  ['The scientists believed the lawyers and the professor . The scientists believed the lawyers ?', True], #temp45_entailment_se_conjunction_subsequence
  ['The authors avoided the managers and the actors . The authors avoided the managers ?', True], #temp45_entailment_se_conjunction_subsequence
  ['Important students introduced the judges . Students introduced the judges ?', True], #temp46_entailment_se_adjective_subsequence
  ['Helpful judges saw the athletes . Judges saw the athletes ?', True], #temp46_entailment_se_adjective_subsequence
  ['The presidents paid the scientists . The presidents paid ?', True], #temp47_entailment_se_understood_object_subsequence
  ['The authors ate the rice . The authors ate ?', True], #temp47_entailment_se_understood_object_subsequence
  ['The managers admired the authors who called the actor . The managers admired the authors ?', True], #temp48_entailment_se_relative_clause_on_obj_subsequence
  ['The artists avoided the athlete that helped the lawyers . The artists avoided the athlete ?', True], #temp48_entailment_se_relative_clause_on_obj_subsequence
  ['The secretaries advised the senators by the athletes . The secretaries advised the senators ?', True], #temp49_entailment_se_PP_on_obj_subsequence
  ['The authors thanked the athletes in front of the lawyers . The authors thanked the athletes ?', True], #temp49_entailment_se_PP_on_obj_subsequence
  ['In case the doctors stopped the author , the bankers helped the manager . The doctors stopped the author ?', None], #temp50_non-entailment_cn_embedded_under_if_constituent
  ['Whether or not the professor danced , the student waited . The professor danced ?', None], #temp50_non-entailment_cn_embedded_under_if_constituent
  ['Unless the professor slept , the tourist saw the scientist . The tourist saw the scientist ?', None], #temp51_non-entailment_cn_after_if_clause_constituent
  ['If the managers advised the artist , the athlete slept . The athlete slept ?', None], #temp51_non-entailment_cn_after_if_clause_constituent
  #['The lawyers believed that the tourists shouted . The tourists shouted ?', None], #temp52_non-entailment_cn_embedded_under_verb_constituent
  #['The lawyers believed that the tourists slept . The tourists slept ?', None], #temp52_non-entailment_cn_embedded_under_verb_constituent
  ['The actor recommended the lawyers , or the managers stopped the author . The actor recommended the lawyers ?', None], #temp53_non-entailment_cn_disjunction_constituent
  ['The student mentioned the artist , or the athletes helped the judges . The athletes helped the judges ?', None], #temp54_non-entailment_cn_disjunction_constituent
  ['The senator admired the authors , or the tourists avoided the student . The tourists avoided the student ?', None], #temp54_non-entailment_cn_disjunction_constituent
  ['The tourists avoided the doctors , or the scientist resigned . The tourists avoided the doctors ?', None], #temp53_non-entailment_cn_disjunction_constituent
  #['Hopefully the presidents introduced the doctors . The presidents introduced the doctors ?', None], #temp58_non-entailment_cn_adverb_constituent
  #['Probably the athletes slept . The athletes slept ?', None], #temp58_non-entailment_cn_adverb_constituent
  ['Before the presidents ran , the tourist shouted . The presidents ran ?', True], #temp59_entailment_ce_embedded_under_since_constituent
  ['Though the doctor recognized the author , the banker supported the lawyers . The doctor recognized the author ?', True], #temp59_entailment_ce_embedded_under_since_constituent
  ['Since the athletes shouted , the actor recognized the professor . The actor recognized the professor ?', True], #temp60_entailment_ce_after_since_clause_constituent
  ['After the manager encouraged the secretaries , the senator danced . The senator danced ?', True], #temp60_entailment_ce_after_since_clause_constituent
  ['The managers knew that the students slept . The students slept ?', True], #temp61_entailment_ce_embedded_under_verb_constituent
  ['The professors knew that the students ran . The students ran ?', True], #temp61_entailment_ce_embedded_under_verb_constituent
  ['The senator saw the authors , and the tourists introduced the presidents . The tourists introduced the presidents ?', True], #temp63_entailment_ce_conjunction_constituent
  ['The students contacted the senators , and the bankers arrived . The students contacted the senators ?', True], #temp62_entailment_ce_conjunction_constituent
  ['The secretary performed , and the president danced . The secretary performed ?', True], #temp62_entailment_ce_conjunction_constituent
  ['The judges shouted , and the scientists recognized the lawyer . The scientists recognized the lawyer ?', True], #temp63_entailment_ce_conjunction_constituent
  ['Clearly the author encouraged the actors . The author encouraged the actors ?', True], #temp68_entailment_ce_adverb_constituent
  ['Of course the doctors saw the secretary . The doctors saw the secretary ?', True] #temp68_entailment_ce_adverb_constituent

]
