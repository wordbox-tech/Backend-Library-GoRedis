# Backend-Library-GoRedis

Library for logging in Go using Uber's zap library

## Execution
1. For Installing, run the next command:
    - `go get -u github.com/wordbox-tech/Backend-Library-GoRedis@vX.X.X`
2. To check if all dependencies are satisfied, run the next command:
    - `go mod tidy -v`

## Usage
import the library
    - `goredis "github.com/wordbox-tech/Backend-Library-GoRedis"`

```go
RedisHelper *goredis.RedisHelper
RedisHelper.Get(KEY_SUFIX, userId, &userCache)
RedisHelper.Set(KEY_SUFIX, userId, user)
RedisHelper.Remove(KEY_SUFIX,userId)
```
