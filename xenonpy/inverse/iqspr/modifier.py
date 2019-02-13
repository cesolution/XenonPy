#  Copyright (c) 2019. yoshida-lab. All rights reserved.
#  Use of this source code is governed by a BSD-style
#  license that can be found in the LICENSE file.

import random
import re
from copy import deepcopy

import numpy as np
import pandas as pd
from rdkit import Chem

from ..base import BaseProposer


class NGram(BaseProposer):
    def __init__(self, *, ngram_tab=None, order=10):
        if ngram_tab is not None:
            self._table = deepcopy(ngram_tab)
            self._order = len(ngram_tab)
        else:
            self._table = [[[], []] for i in range(order)]
            self._order = order

    def modify(self, ext_smi, n=8, p=0.5):

        # esmi_pd = reorder_esmi(esmi_pd)
        # number of add/delete (n) with probability of add = p
        n_add = sum(np.random.choice([False, True], n, p=[1 - p, p]))
        # first delete then add
        ext_smi = self.del_char(ext_smi, min(n - n_add + 1, len(ext_smi) - 1))  # at least leave 1 character
        for i in range(n_add):
            ext_smi, _ = self.sample_next_char(ext_smi)
            if ext_smi['esmi'].iloc[-1] == '!':
                return ext_smi  # stop when hitting '!', assume must be valid SMILES
        ext_smi = self.validator(ext_smi)
        new_pd_row = {
            'esmi': '!',
            'n_br': 0,
            'n_ring': 0,
            'substr': ext_smi['substr'].iloc[-1] + ['!']
        }
        return ext_smi.append(new_pd_row, ignore_index=True)

    @classmethod
    def smi2list(cls, smiles):
        # smi_pat = '(=\[.*?\]|#\[.*?\]|\[.*?\]|=Br|#Br|=Cl|#Cl|Br|Cl|=.|#.|\%[0-9][0-9]|\w|\W)'
        smi_pat = r'(\[.*?\]|Br|Cl|\%[0-9][0-9]|\w|\W)'
        smi_list = list(filter(None, re.split(smi_pat, smiles)))
        return smi_list

    @classmethod
    def smi2esmi(cls, smi):
        smi_list = cls.smi2list(smi)

        esmi_list = smi_list + ['!']
        substr_list = []  # list of all contracted substrings (include current char.)
        br_list = [
        ]  # list of whether open branch exist at current character position (include current char.)
        ring_list = [
        ]  # list of number of open ring at current character position (include current char.)
        v_substr = []  # list of temporary contracted substrings
        v_ringn = []  # list of numbering of open rings
        c_br = 0  # tracking open branch steps for recording contracted substrings
        n_br = 0  # tracking number of open branches
        tmp_ss = []  # list of current contracted substring
        for i in range(len(esmi_list)):
            if c_br == 2:
                v_substr.append(deepcopy(tmp_ss))  # contracted substring added w/o ')'
                c_br = 0
            elif c_br == 1:
                c_br = 2

            if esmi_list[i] == '(':
                c_br = 1
                n_br += 1
            elif esmi_list[i] == ')':
                tmp_ss = deepcopy(v_substr[-1])  # retrieve contracted substring added w/o ')'
                v_substr.pop()
                n_br -= 1
            elif '%' in esmi_list[i]:
                esmi_list[i] = int(esmi_list[i][1:3])
                if esmi_list[i] in v_ringn:
                    esmi_list[i] = v_ringn.index(esmi_list[i])
                    v_ringn.pop(esmi_list[i])
                else:
                    v_ringn.append(esmi_list[i])
                    esmi_list[i] = '&'
            elif esmi_list[i].isdigit():
                esmi_list[i] = int(esmi_list[i])
                if esmi_list[i] in v_ringn:
                    esmi_list[i] = v_ringn.index(esmi_list[i])
                    v_ringn.pop(esmi_list[i])
                else:
                    v_ringn.append(esmi_list[i])
                    esmi_list[i] = '&'

            tmp_ss.append(esmi_list[i])
            substr_list.append(deepcopy(tmp_ss))
            br_list.append(n_br)
            ring_list.append(len(v_ringn))

        return pd.DataFrame({
            'esmi': esmi_list,
            'n_br': br_list,
            'n_ring': ring_list,
            'substr': substr_list
        })

    # may add error check here in the future?
    @classmethod
    def esmi2smi(cls, ext_smi):
        smi_list = ext_smi['esmi'].tolist()
        num_open = []
        num_unused = list(range(99, 0, -1))
        for i in range(len(smi_list)):
            if smi_list[i] == '&':
                if num_unused[-1] > 9:
                    smi_list[i] = ''.join(['%', str(num_unused[-1])])
                else:
                    smi_list[i] = str(num_unused[-1])
                num_open.insert(0, num_unused[-1])
                num_unused.pop()
            elif isinstance(smi_list[i], int):
                tmp = int(smi_list[i])
                if num_open[tmp] > 9:
                    smi_list[i] = ''.join(['%', str(num_open[tmp])])
                else:
                    smi_list[i] = str(num_open[tmp])
                num_unused.append(num_open[tmp])
                num_open.pop(tmp)
        if smi_list[-1] == "!":  # cover cases of incomplete esmi_pd
            smi_list.pop()  # remove the final '!'
        return ''.join(smi_list)

    def fit(self, smis, **kwargs):
        def _fit_one(ext_smi):
            for iB in [False, True]:
                # index for open/closed branches char. position, remove last row for '!'
                idx_B = ext_smi.iloc[:-1].index[(ext_smi['n_br'].iloc[:-1] > 0) == iB]
                list_R = ext_smi['n_ring'][idx_B].unique().tolist()
                if len(list_R) > 0:
                    if len(self._table[0][iB]) < (
                            max(list_R) + 1):  # expand list of dataframe for max. num-of-ring + 1
                        for ii in range(len(self._table)):
                            self._table[ii][iB].extend([
                                pd.DataFrame()
                                for i in range((max(list_R) + 1) - len(self._table[ii][iB]))
                            ])
                    for iR in list_R:
                        # index for num-of-open-ring char. pos.
                        idx_R = idx_B[ext_smi['n_ring'][idx_B] == iR]

                        # shift one down for 'next character given substring'
                        tar_char = ext_smi['esmi'][idx_R + 1].tolist()
                        tar_substr = ext_smi['substr'][idx_R].tolist()

                        for iO in range(len(self._table)):
                            # index for char with substring length not less than order
                            idx_O = [x for x in range(len(tar_substr)) if len(tar_substr[x]) > iO]
                            for iC in idx_O:
                                if not tar_char[iC] in self._table[iO][iB][iR].columns.tolist():
                                    self._table[iO][iB][iR][tar_char[iC]] = 0
                                tmp_row = str(tar_substr[iC][-(iO + 1):])
                                if tmp_row not in self._table[iO][iB][iR].index.tolist():
                                    self._table[iO][iB][iR].loc[tmp_row] = 0

                                # somehow 'at' not ok with mixed char and int column names
                                self._table[iO][iB][iR].loc[tmp_row, tar_char[iC]] += 1

        for smi in smis:
            _fit_one(self.smi2esmi(smi))

        return self

    # get probability vector for sampling next character, return character list and corresponding probability in numpy.array (normalized)
    # may cause error if empty string list is fed into 'tmp_str'
    # Warning: maybe can reduce the input of iB and iR - directly input the reduced list of self._ngram_tab (?)
    # Warning: may need to update this function with bisection search for faster speed (?)
    # Warning: may need to add worst case that no pattern found at all?
    def get_prob(self, tmp_str, iB, iR):
        # right now we use back-off method, an alternative is Kneser–Nay smoothing
        for iO in range(len(self._table) - 1, -1, -1):
            if (len(tmp_str) > iO) & (str(
                    tmp_str[-(iO + 1):]) in self._table[iO][iB][iR].index.tolist()):
                cand_char = self._table[iO][iB][iR].columns.tolist()
                cand_prob = np.array(self._table[iO][iB][iR].loc[str(tmp_str[-(iO + 1):])])
                break
        return cand_char, cand_prob / sum(cand_prob)

    # get the next character, return the probability value
    def sample_next_char(self, ext_smi):
        iB = ext_smi['n_br'].iloc[-1] > 0
        iR = ext_smi['n_ring'].iloc[-1]
        cand_char, cand_prob = self.get_prob(ext_smi['substr'].iloc[-1], iB, iR)
        # here we assume cand_char is not empty
        tmp = random.choices(range(len(cand_char)), weights=cand_prob)
        ext_smi = self.add_char(ext_smi, cand_char[tmp[0]])
        return ext_smi, cand_prob[tmp[0]]

    @classmethod
    def add_char(cls, ext_smi, next_char):
        new_pd_row = ext_smi.iloc[-1]
        new_pd_row.at['substr'] = new_pd_row['substr'] + [next_char]
        new_pd_row.at['esmi'] = next_char
        if next_char == '(':
            new_pd_row.at['n_br'] += 1
        elif next_char == ')':
            new_pd_row.at['n_br'] -= 1
            # assume '(' must exist before if the extended SMILES is valid! (will fail if violated)
            # idx = next((x for x in range(len(new_pd_row['substr'])-1,-1,-1) if new_pd_row['substr'][x] == '('), None)
            # find index of the last unclosed '('
            tmp_c = 1
            for x in range(len(new_pd_row['substr']) - 2, -1,
                           -1):  # exclude the already added "next_char"
                if new_pd_row['substr'][x] == '(':
                    tmp_c -= 1
                elif new_pd_row['substr'][x] == ')':
                    tmp_c += 1
                if tmp_c == 0:
                    idx = x
                    break
            # assume no '()' and '((' pattern that is not valid/possible in SMILES
            new_pd_row.at['substr'] = new_pd_row['substr'][:(idx + 2)] + [')']
        elif next_char == '&':
            new_pd_row.at['n_ring'] += 1
        elif isinstance(next_char, int):
            new_pd_row.at['n_ring'] -= 1
        return ext_smi.append(new_pd_row, ignore_index=True)

    @classmethod
    def del_char(cls, ext_smi, n_char):
        return ext_smi[:-n_char]

    # need to make sure esmi_pd is a completed SMILES to use this function
    @classmethod
    def reorder_esmi(cls, ext_smi):
        # convert back to SMILES first, then to rdkit MOL
        m = Chem.MolFromSmiles(cls.esmi2smi(ext_smi))
        idx = np.random.choice(range(m.GetNumAtoms()))
        # currently assume kekuleSmiles=True, i.e., no small letters but with ':' for aromatic rings
        ext_smi = cls.smi2esmi(Chem.MolToSmiles(m, rootedAtAtom=idx, kekuleSmiles=True))
        return ext_smi

    def validator(self, ext_smi):
        # delete all ending '(' or '&'
        for i in range(len(ext_smi)):
            if not ((ext_smi['esmi'].iloc[-1] == '(') | (ext_smi['esmi'].iloc[-1] == '&')):
                break
            ext_smi = self.del_char(ext_smi, 1)
        # delete or fill in ring closing
        flag_ring = ext_smi['n_ring'].iloc[-1] > 0
        for i in range(len(ext_smi)):  # max to double the length of current SMILES
            if flag_ring and (np.random.random() < 0.7):  # 50/50 for adding two new char.
                # add a character
                ext_smi, _ = self.sample_next_char(ext_smi)
                flag_ring = ext_smi['n_ring'].iloc[-1] > 0
            else:
                break
        if flag_ring:
            # prepare for delete (1st letter shall not be '&')
            tmp_idx = ext_smi.iloc[1:].index
            tmp_count = np.array(ext_smi['n_ring'].iloc[1:]) - np.array(ext_smi['n_ring'].iloc[:-1])
            num_open = tmp_idx[tmp_count == 1]
            num_close = ext_smi['esmi'][tmp_count == -1]
            for i in num_close:
                num_open.pop(i)
            # delete all irrelevant rows and reconstruct esmi
            ext_smi = self.smi2esmi(
                self.esmi2smi(ext_smi.drop(ext_smi.index[num_open]).reset_index(drop=True)))
        # fill in branch closing (last letter shall not be '(')
        for i in range(ext_smi['n_br'].iloc[-1]):
            ext_smi = self.add_char(ext_smi, ')')

        return ext_smi

    def proposal(self, smis, size, *, p=None):
        smis = np.random.choice(smis, size, p=p)
        new_smis = []
        for i, smi in enumerate(smis):
            ext_smi = self.smi2esmi(smi)
            new_ext_smi = self.modify(ext_smi)
            new_smi = self.esmi2smi(new_ext_smi)
            if Chem.MolFromSmiles(new_smi) is not None:
                new_smis.append(new_smi)

        return new_smis