#include <algorithm>
#include <array>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>
#include <vector>

#ifdef __EMSCRIPTEN__
#include <emscripten.h>
#define C4_EXPORT EMSCRIPTEN_KEEPALIVE
#else
#define C4_EXPORT
#endif

namespace {

constexpr int WIDTH = 7;
constexpr int HEIGHT = 6;
constexpr int STRIDE = 7;
constexpr int CELLS = WIDTH * HEIGHT;
constexpr int SHIFTS[4] = {1, 7, 6, 8};

struct Position {
    uint64_t current = 0;
    uint64_t mask = 0;
    int moves = 0;

    bool play(int col) {
        if (col < 0 || col >= WIDTH) return false;
        uint64_t move = (mask + (1ULL << (col * STRIDE))) & (1ULL << (col * STRIDE + HEIGHT - 1));
        if (!move) {
            uint64_t column = ((1ULL << HEIGHT) - 1) << (col * STRIDE);
            uint64_t occupied = mask & column;
            int level = 0;
            while (level < HEIGHT && (occupied & (1ULL << (col * STRIDE + level)))) ++level;
            if (level == HEIGHT) return false;
            move = 1ULL << (col * STRIDE + level);
        }
        current ^= mask;
        mask |= move;
        ++moves;
        return true;
    }

    uint64_t player_to_move() const {
        return current;
    }

    bool won(uint64_t bits) const {
        for (int shift : SHIFTS) {
            uint64_t pair = bits & (bits >> shift);
            if (pair & (pair >> (2 * shift))) return true;
        }
        return false;
    }

    uint64_t legal_moves() const {
        uint64_t result = 0;
        for (int col = 0; col < WIDTH; ++col) {
            int level = 0;
            while (level < HEIGHT && (mask & (1ULL << (col * STRIDE + level)))) ++level;
            if (level < HEIGHT) result |= 1ULL << (col * STRIDE + level);
        }
        return result;
    }

    uint64_t winning_moves(uint64_t stones) const {
        uint64_t result = 0;
        uint64_t moves_mask = legal_moves();
        while (moves_mask) {
            uint64_t move = moves_mask & -moves_mask;
            moves_mask ^= move;
            if (won(stones | move)) result |= move;
        }
        return result;
    }

    uint64_t non_losing_moves() const {
        uint64_t candidates = legal_moves();
        uint64_t safe = 0;
        while (candidates) {
            uint64_t move = candidates & -candidates;
            candidates ^= move;
            if (won(current | move)) return move;
            uint64_t next_mask = mask | move;
            uint64_t next_player = current ^ mask;
            bool opponent_can_win = false;
            for (int col = 0; col < WIDTH; ++col) {
                int level = 0;
                while (level < HEIGHT && (next_mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level == HEIGHT) continue;
                uint64_t reply = 1ULL << (col * STRIDE + level);
                if (won(next_player | reply)) {
                    opponent_can_win = true;
                    break;
                }
            }
            if (!opponent_can_win) safe |= move;
        }
        return safe;
    }

    static uint64_t mirror(uint64_t bits) {
        uint64_t result = 0;
        for (int col = 0; col < WIDTH; ++col) {
            for (int row = 0; row < HEIGHT; ++row) {
                uint64_t bit = 1ULL << (col * STRIDE + row);
                if (bits & bit)
                    result |= 1ULL << ((WIDTH - 1 - col) * STRIDE + row);
            }
        }
        return result;
    }

    uint64_t key() const {
        uint64_t a = current + mask;
        uint64_t mirrored = mirror(current) + mirror(mask);
        return std::min(a, mirrored);
    }
};

#if defined(__EMSCRIPTEN__)
constexpr uint32_t TABLE_BITS = 18;
#else
constexpr uint32_t TABLE_BITS = 22;
#endif
constexpr uint32_t TABLE_SIZE = 1U << TABLE_BITS;
constexpr uint32_t TABLE_MASK = TABLE_SIZE - 1;

struct Entry {
    uint64_t key = 0;
    int16_t score = 0;
    uint8_t flag = 0;
    uint8_t best = 0;
};

class Solver {
    std::vector<Entry> table;
    uint64_t nodes = 0;

    static int column_order[WIDTH];

    static uint64_t hash_key(uint64_t key) {
        key ^= key >> 30;
        key *= 0xbf58476d1ce4e5b9ULL;
        key ^= key >> 27;
        key *= 0x94d049bb133111ebULL;
        key ^= key >> 31;
        return key;
    }

    int search(const Position& p, int alpha, int beta) {
        ++nodes;
        uint64_t legal = p.legal_moves();
        if (!legal) return 0;

        uint64_t immediate = 0;
        uint64_t scan = legal;
        while (scan) {
            uint64_t move = scan & -scan;
            scan ^= move;
            if (p.won(p.current | move)) {
                return (CELLS + 1 - p.moves) / 2;
            }
        }

        if (p.moves >= CELLS - 2) return 0;

        int original_alpha = alpha;
        uint64_t key = p.key();
        Entry& entry = table[hash_key(key) & TABLE_MASK];
        int preferred = -1;
        if (entry.flag && entry.key == key) {
            preferred = entry.best;
            if (entry.flag == 1) return entry.score;
            if (entry.flag == 2) alpha = std::max(alpha, static_cast<int>(entry.score));
            if (entry.flag == 3) beta = std::min(beta, static_cast<int>(entry.score));
            if (alpha >= beta) return entry.score;
        }

        uint64_t moves = p.non_losing_moves();
        if (!moves) return -((CELLS - p.moves) / 2);

        int best_score = -100;
        int best_col = -1;
        for (int i = 0; i < WIDTH; ++i) {
            int col = column_order[i];
            uint64_t move = 0;
            if (col == preferred) {
                int level = 0;
                while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level < HEIGHT) move = 1ULL << (col * STRIDE + level);
            }
            if (!move) {
                int level = 0;
                while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level < HEIGHT) move = 1ULL << (col * STRIDE + level);
            }
            if (!(moves & move)) continue;

            Position child = p;
            child.current ^= child.mask;
            child.mask |= move;
            ++child.moves;
            int score = -search(child, -beta, -alpha);
            if (score > best_score) {
                best_score = score;
                best_col = col;
            }
            alpha = std::max(alpha, score);
            if (alpha >= beta) break;
        }

        Entry updated;
        updated.key = key;
        updated.score = static_cast<int16_t>(best_score);
        updated.best = static_cast<uint8_t>(best_col < 0 ? 0 : best_col);
        updated.flag = best_score <= original_alpha ? 3 : best_score >= beta ? 2 : 1;
        entry = updated;
        return best_score;
    }

public:
    Solver() : table(TABLE_SIZE) {}

    int best_move(const Position& p) {
        nodes = 0;
        uint64_t legal = p.legal_moves();
        if (!legal) return -1;
        for (int col : column_order) {
            int level = 0;
            while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
            if (level < HEIGHT && p.won(p.current | (1ULL << (col * STRIDE + level))))
                return col;
        }

        uint64_t moves = p.non_losing_moves();
        if (!moves) {
            for (int col : column_order) {
                int level = 0;
                while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level < HEIGHT) return col;
            }
        }

        int best = -100;
        int best_col = -1;
        int alpha = -100;
        for (int col : column_order) {
            int level = 0;
            while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
            if (level == HEIGHT) continue;
            uint64_t move = 1ULL << (col * STRIDE + level);
            if (!(moves & move)) continue;
            Position child = p;
            child.current ^= child.mask;
            child.mask |= move;
            ++child.moves;
            int score = -search(child, -100, -alpha);
            if (score > best) {
                best = score;
                best_col = col;
            }
            alpha = std::max(alpha, score);
        }
        return best_col;
    }

    uint64_t node_count() const { return nodes; }
};

int Solver::column_order[WIDTH] = {3, 2, 4, 1, 5, 0, 6};

Solver solver;

bool parse_position(const char* sequence, Position& p) {
    if (!sequence) return false;
    for (const char* ch = sequence; *ch; ++ch) {
        if (*ch < '1' || *ch > '7') return false;
        int col = *ch - '1';
        uint64_t move = p.legal_moves() & (((1ULL << HEIGHT) - 1) << (col * STRIDE));
        if (!move) return false;
        move &= -move;
        bool was_winning = p.won(p.current | move);
        p.current ^= p.mask;
        p.mask |= move;
        ++p.moves;
        if (was_winning && *(ch + 1)) return false;
    }
    return true;
}

}

extern "C" {

C4_EXPORT int c4_best_move(const char* sequence) {
    Position p;
    if (!parse_position(sequence, p)) return -1;
    return solver.best_move(p);
}

C4_EXPORT int c4_score(const char* sequence) {
    Position p;
    if (!parse_position(sequence, p)) return -100;
    return solver.best_move(p);
}

C4_EXPORT int c4_analyze(const char* sequence, int* output) {
    Position p;
    if (!parse_position(sequence, p) || !output) return 0;
    auto scores = solver.analyze(p);
    for (int i = 0; i < WIDTH; ++i) output[i] = scores[i];
    return 1;
}

C4_EXPORT double c4_nodes() {
    return static_cast<double>(solver.node_count());
}

}

#ifndef __EMSCRIPTEN__
int main() {
    std::string line;
    while (std::getline(std::cin, line)) {
        Position p;
        if (!parse_position(line.c_str(), p)) {
            std::cout << "-1 -100 0\n";
            continue;
        }
        int move = solver.best_move(p);
        std::cout << move << " 0 " << solver.node_count() << "\n";
    }
    return 0;
}
#endif
