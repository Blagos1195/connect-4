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
        for (int shift : SHIFTS) {
            uint64_t three = (stones >> shift) & (stones >> (2 * shift)) & (stones >> (3 * shift));
            result |= three;
            three = stones & (stones >> shift) & (stones >> (2 * shift));
            result |= three << (3 * shift);
            three = stones & (stones >> (2 * shift)) & (stones >> (3 * shift));
            result |= three << shift;
            three = stones & (stones >> shift) & (stones >> (3 * shift));
            result |= three << (2 * shift);
        }
        return result & legal_moves();
    }

    uint64_t non_losing_moves() const {
        uint64_t wins = winning_moves(current);
        if (wins) return wins;
        uint64_t threats = winning_moves(current ^ mask);
        if (__builtin_popcountll(threats) > 1) return 0;
        if (threats) return threats;
        return legal_moves();
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

    bool is_mirrored() const {
        return mirror(current) + mirror(mask) < current + mask;
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

        uint64_t scan = legal;
        while (scan) {
            uint64_t move = scan & -scan;
            scan ^= move;
            if (p.won(p.current | move))
                return (CELLS + 1 - p.moves) / 2;
        }

        uint64_t moves = p.non_losing_moves();
        if (!moves) return -((CELLS - p.moves) / 2);
        if (p.moves >= CELLS - 2) return 0;

        int lower = -((CELLS - p.moves) / 2);
        int upper = (CELLS - 1 - p.moves) / 2;
        if (alpha < lower) {
            alpha = lower;
            if (alpha >= beta) return alpha;
        }
        if (beta > upper) {
            beta = upper;
            if (alpha >= beta) return beta;
        }

        int original_alpha = alpha;
        int original_beta = beta;
        uint64_t key = p.key();
        Entry& entry = table[hash_key(key) & TABLE_MASK];
        int preferred = -1;
        bool reflected = p.is_mirrored();
        if (entry.flag && entry.key == key) {
            preferred = reflected ? WIDTH - 1 - entry.best : entry.best;
            if (entry.flag == 1) return entry.score;
            if (entry.flag == 2) alpha = std::max(alpha, static_cast<int>(entry.score));
            if (entry.flag == 3) beta = std::min(beta, static_cast<int>(entry.score));
            if (alpha >= beta) return entry.score;
        }

        int best_score = -100;
        int best_col = -1;
        for (int i = 0; i < WIDTH; ++i) {
            int col = preferred >= 0 && i == 0 ? preferred : column_order[i];
            int level = 0;
            while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
            if (level == HEIGHT) continue;
            uint64_t move = 1ULL << (col * STRIDE + level);
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
        updated.best = static_cast<uint8_t>(best_col < 0 ? 0 : reflected ? WIDTH - 1 - best_col : best_col);
        updated.flag = best_score <= original_alpha ? 3 : best_score >= original_beta ? 2 : 1;
        entry = updated;
        return best_score;
    }

    int solve(const Position& p) {
        uint64_t legal = p.legal_moves();
        uint64_t scan = legal;
        while (scan) {
            uint64_t move = scan & -scan;
            scan ^= move;
            if (p.won(p.current | move))
                return (CELLS + 1 - p.moves) / 2;
        }

        int lower = -((CELLS - p.moves) / 2);
        int upper = (CELLS + 1 - p.moves) / 2;
        while (lower < upper) {
            int middle = lower + (upper - lower) / 2;
            if (middle <= 0 && lower / 2 < middle) middle = lower / 2;
            else if (middle >= 0 && upper / 2 > middle) middle = upper / 2;
            int result = search(p, middle, middle + 1);
            if (result <= middle) upper = result;
            else lower = result;
        }
        return lower;
    }

public:
    Solver() : table(TABLE_SIZE) {}

    std::array<int, WIDTH> analyze(const Position& p) {
        nodes = 0;
        std::array<int, WIDTH> scores;
        scores.fill(-1000);
        for (int col = 0; col < WIDTH; ++col) {
            int level = 0;
            while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
            if (level == HEIGHT) continue;
            uint64_t move = 1ULL << (col * STRIDE + level);
            if (p.won(p.current | move)) {
                scores[col] = (CELLS + 1 - p.moves) / 2;
                continue;
            }
            Position child = p;
            child.current ^= child.mask;
            child.mask |= move;
            ++child.moves;
            scores[col] = -solve(child);
        }
        return scores;
    }

    int best_move(const Position& p) {
        uint64_t legal = p.legal_moves();
        if (!legal) return -1;

        uint64_t wins = p.winning_moves(p.current);
        if (wins) {
            for (int col : column_order) {
                int level = 0;
                while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level < HEIGHT && (wins & (1ULL << (col * STRIDE + level))) &&
                    p.won(p.current | (1ULL << (col * STRIDE + level)))) return col;
            }
        }

        uint64_t safe = p.non_losing_moves();
        if (!safe) {
            for (int col : column_order) {
                int level = 0;
                while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level < HEIGHT) return col;
            }
        }

        if (p.moves >= CELLS - 2) {
            for (int col : column_order) {
                int level = 0;
                while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
                if (level < HEIGHT && (safe & (1ULL << (col * STRIDE + level)))) return col;
            }
        }

        int value = solve(p);
        search(p, value - 1, value);

        uint64_t key = p.key();
        const Entry& entry = table[hash_key(key) & TABLE_MASK];
        if (entry.flag && entry.key == key) {
            int col = p.is_mirrored() ? WIDTH - 1 - entry.best : entry.best;
            int level = 0;
            while (level < HEIGHT && (p.mask & (1ULL << (col * STRIDE + level)))) ++level;
            if (level < HEIGHT && (safe & (1ULL << (col * STRIDE + level)))) return col;
        }

        auto scores = analyze(p);
        int best_score = -1000;
        int best_col = -1;
        for (int col : column_order) {
            if (scores[col] > best_score) {
                best_score = scores[col];
                best_col = col;
            }
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
