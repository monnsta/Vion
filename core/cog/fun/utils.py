# Copyright (c) 2026 monnsta. All rights reserved.

import random


class TicTacToeBot:
	@staticmethod
	def _minimax(board, depth, is_maximizing, bot_mark, human_mark):
		winner = TicTacToeBot.check_win(board)
		if winner == bot_mark:
			return 10 - depth
		if winner == human_mark:
			return depth - 10
		if winner == "Tie":
			return 0

		available = [i for i, v in enumerate(board) if v is None]

		if is_maximizing:
			best_score = -float('inf')
			for i in available:
				board[i] = bot_mark
				score = TicTacToeBot._minimax(board, depth + 1, False, bot_mark, human_mark)
				board[i] = None
				best_score = max(score, best_score)
			return best_score
		else:
			best_score = float('inf')
			for i in available:
				board[i] = human_mark
				score = TicTacToeBot._minimax(board, depth + 1, True, bot_mark, human_mark)
				board[i] = None
				best_score = min(score, best_score)
			return best_score

	@staticmethod
	def get_move(board: list, bot_mark: str, human_mark: str, difficulty: int) -> int:
		available = [i for i, v in enumerate(board) if v is None]

		if not available:
			return -1

		if difficulty == 0 or (difficulty == 1 and random.random() < 0.5):
			return random.choice(available)

		best_score = -float('inf')
		best_move = -1

		for i in available:
			board[i] = bot_mark
			score = TicTacToeBot._minimax(board, 0, False, bot_mark, human_mark)
			board[i] = None
			if score > best_score:
				best_score = score
				best_move = i

		return best_move

	@staticmethod
	def check_win(board):
		win_states = [
			[0, 1, 2], [3, 4, 5], [6, 7, 8],
			[0, 3, 6], [1, 4, 7], [2, 5, 8],
			[0, 4, 8], [2, 4, 6]
		]
		for state in win_states:
			if board[state[0]] is not None and board[state[0]] == board[state[1]] == board[state[2]]:
				return board[state[0]]
		if None not in board:
			return "Tie"
		return None


class TicTacToeSixBySevenBot:
	WINDOWS = []
	for r in range(6):
		for c in range(4): WINDOWS.append((r * 7 + c, r * 7 + c + 1, r * 7 + c + 2, r * 7 + c + 3))
	for r in range(3):
		for c in range(7): WINDOWS.append((r * 7 + c, (r + 1) * 7 + c, (r + 2) * 7 + c, (r + 3) * 7 + c))
	for r in range(3):
		for c in range(4): WINDOWS.append((r * 7 + c, (r + 1) * 7 + c + 1, (r + 2) * 7 + c + 2, (r + 3) * 7 + c + 3))
	for r in range(3):
		for c in range(3, 7): WINDOWS.append((r * 7 + c, (r + 1) * 7 + c - 1, (r + 2) * 7 + c - 2, (r + 3) * 7 + c - 3))

	MOVE_PRIORITY = {i: abs((i % 7) - 3) + abs((i // 7) - 2.5) for i in range(42)}

	ADJACENT_MAP = {}
	for r in range(6):
		for c in range(7):
			idx = r * 7 + c
			neighbors = []
			for dr in [-1, 0, 1]:
				for dc in [-1, 0, 1]:
					if dr == 0 and dc == 0: continue
					nr, nc = r + dr, c + dc
					if 0 <= nr < 6 and 0 <= nc < 7:
						neighbors.append(nr * 7 + nc)
			ADJACENT_MAP[idx] = neighbors

	TT = {}

	@classmethod
	def _get_candidate_moves(cls, board: list) -> list:
		moves = set()
		has_pieces = False
		for i, val in enumerate(board):
			if val is not None:
				has_pieces = True
				for neighbor in cls.ADJACENT_MAP[i]:
					if board[neighbor] is None:
						moves.add(neighbor)
		return list(moves) if has_pieces else [24]

	@classmethod
	def _evaluate_board(cls, board: list, bot_mark: str, human_mark: str) -> int:
		score = 0
		for i1, i2, i3, i4 in cls.WINDOWS:
			b1, b2, b3, b4 = board[i1], board[i2], board[i3], board[i4]

			bot_count = (b1 == bot_mark) + (b2 == bot_mark) + (b3 == bot_mark) + (b4 == bot_mark)
			human_count = (b1 == human_mark) + (b2 == human_mark) + (b3 == human_mark) + (b4 == human_mark)

			if bot_count > 0 and human_count == 0:
				if bot_count == 4: score += 1000
				elif bot_count == 3: score += 100
				elif bot_count == 2: score += 10
			elif human_count > 0 and bot_count == 0:
				if human_count == 4: score -= 1000
				elif human_count == 3: score -= 500
				elif human_count == 2: score -= 12
		return score

	@classmethod
	def _minimax(cls, board: list, depth: int, alpha: float, beta: float, is_maximizing: bool, bot_mark: str, human_mark: str) -> int:
		board_tuple = tuple(board)
		if board_tuple in cls.TT and cls.TT[board_tuple][1] >= depth:
			return cls.TT[board_tuple][0]

		winner = cls.check_win(board)
		if winner == bot_mark: return 1000000 + depth
		if winner == human_mark: return -1000000 - depth
		if winner == "Tie" or depth == 0:
			eval_val = cls._evaluate_board(board, bot_mark, human_mark)
			cls.TT[board_tuple] = (eval_val, depth)
			return eval_val

		moves = cls._get_candidate_moves(board)
		moves.sort(key=cls.MOVE_PRIORITY.get)

		if is_maximizing:
			max_eval = -float('inf')
			for move in moves:
				board[move] = bot_mark
				eval_val = cls._minimax(board, depth - 1, alpha, beta, False, bot_mark, human_mark)
				board[move] = None
				max_eval = max(max_eval, eval_val)
				alpha = max(alpha, eval_val)
				if beta <= alpha: break
			cls.TT[board_tuple] = (max_eval, depth)
			return max_eval
		else:
			min_eval = float('inf')
			for move in moves:
				board[move] = human_mark
				eval_val = cls._minimax(board, depth - 1, alpha, beta, True, bot_mark, human_mark)
				board[move] = None
				min_eval = min(min_eval, eval_val)
				beta = min(beta, eval_val)
				if beta <= alpha: break
			cls.TT[board_tuple] = (min_eval, depth)
			return min_eval

	@classmethod
	def get_move(cls, board: list, bot_mark: str, human_mark: str, difficulty: int) -> int:
		cls.TT.clear()
		moves = cls._get_candidate_moves(board)
		if not moves: return -1
		if difficulty == 0: return random.choice(moves)

		for move in moves:
			board[move] = bot_mark
			if cls.check_win(board) == bot_mark:
				board[move] = None
				return move
			board[move] = None

		for move in moves:
			board[move] = human_mark
			if cls.check_win(board) == human_mark:
				board[move] = None
				return move
			board[move] = None

		moves.sort(key=cls.MOVE_PRIORITY.get)
		best_score = -float('inf')
		best_move = moves[0]
		search_depth = 4 if difficulty > 1 else 3

		for move in moves:
			board[move] = bot_mark
			score = cls._minimax(board, search_depth, -float('inf'), float('inf'), False, bot_mark, human_mark)
			board[move] = None
			if score > best_score:
				best_score = score
				best_move = move

		return best_move

	@classmethod
	def check_win(cls, board: list):
		for i1, i2, i3, i4 in cls.WINDOWS:
			b1 = board[i1]
			if b1 is not None and b1 == board[i2] == board[i3] == board[i4]:
				return b1
		return "Tie" if None not in board else None


class AvatarRPS:
	_WIN_MATRIX = {
		'water': ['fire', 'earth'],
		'earth': ['fire', 'air'],
		'fire': ['air'],
		'air': ['water']
	}

	@classmethod
	def resolve(cls, p1_choice: str, p2_choice: str) -> str:
		if p1_choice == p2_choice:
			return "tie"

		if p2_choice in cls._WIN_MATRIX[p1_choice]:
			return "p1"
		elif p1_choice in cls._WIN_MATRIX[p2_choice]:
			return "p2"
