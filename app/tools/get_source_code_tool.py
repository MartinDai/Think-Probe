from agents import function_tool


@function_tool(
    name_override="get_source_code_tool",
    description_override="a helpful tool to get java class source code by class full name."
)
def get_source_code_tool(class_full_name: str) -> str:
    print(f"get_source_code_tool class_full_name:{class_full_name}")

    mock_code = """
    package com.doodl6.springboot.web.controller;

    import com.doodl6.springboot.common.check.CheckUtil;
    import com.doodl6.springboot.common.web.response.BaseResponse;
    import com.doodl6.springboot.common.web.response.MapResponse;
    import com.doodl6.springboot.web.request.CheckParameterRequest;
    import com.doodl6.springboot.web.response.CheckParameterResult;
    import io.swagger.v3.oas.annotations.Operation;
    import io.swagger.v3.oas.annotations.tags.Tag;
    import lombok.extern.slf4j.Slf4j;
    import org.springframework.util.Assert;
    import org.springframework.web.bind.annotation.GetMapping;
    import org.springframework.web.bind.annotation.PostMapping;
    import org.springframework.web.bind.annotation.RequestBody;
    import org.springframework.web.bind.annotation.RestController;
    
    /**
     * 常规控制类
     */
    @Tag(name = "常规接口")
    @Slf4j
    @RestController
    public class StandardController {
    
        /**
         * 普通接口
         */
        @Operation(summary = "普通接口")
        @GetMapping("/hello")
        public MapResponse hello(String name) throws InterruptedException {
            MapResponse mapResponse = new MapResponse();
            Assert.notNull(name, "name不能为空");
            Thread.sleep(3000);
    
            mapResponse.appendData("name", name);
    
            return mapResponse;
        }
    
    }
    """

    return mock_code
